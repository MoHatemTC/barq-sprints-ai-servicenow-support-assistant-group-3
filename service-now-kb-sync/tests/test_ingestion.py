from datetime import UTC, datetime, timedelta

import pytest

from app.exceptions import ConfigurationError  # noqa: F401
from app.services.state import SyncStateStore
from tests.conftest import FakeEmbedder, make_article


def test_new_article_is_created(make_service, repo):
    article = make_article()
    service, _ = make_service([article])
    result = service.process_article(article)
    assert result.action == "created"
    assert result.chunks > 1
    assert repo.count_article_points("a1") == result.chunks


def test_sync_is_idempotent(make_service, repo):
    article = make_article()
    service, _ = make_service([article])
    first = service.process_article(article)
    second = service.process_article(article)
    assert (first.action, second.action) == ("created", "updated")
    assert first.chunks == second.chunks
    assert repo.count_article_points("a1") == first.chunks  # no duplicate vectors


def test_update_deletes_old_chunks_before_upserting(make_service, repo):
    service, _ = make_service()
    service.process_article(make_article(text="<p>" + "old content here. " * 80 + "</p>"))
    repo.log.clear()

    result = service.process_article(make_article(text="<p>Totally new short text.</p>"))

    assert result.action == "updated"
    assert repo.log == ["delete", "upsert"]  # delete strictly before upsert
    assert repo.count_article_points("a1") == 1  # old extra chunks are gone, not appended
    stale = repo._client.scroll("test_kb", limit=100)[0]
    assert all("old content" not in p.payload["text"] for p in stale)


def test_unpublished_article_is_removed(make_service, repo):
    service, _ = make_service()
    service.process_article(make_article())
    assert repo.article_exists("a1")

    result = service.process_article(make_article(workflow_state="retired", published=False))
    assert result.action == "deleted"
    assert not repo.article_exists("a1")


def test_unpublished_unknown_article_is_skipped(make_service, repo):
    service, _ = make_service()
    result = service.process_article(make_article(workflow_state="draft", published=False))
    assert result.action == "skipped"
    assert repo.count_article_points("a1") == 0


def test_published_article_with_empty_body_removes_vectors(make_service, repo):
    service, _ = make_service()
    service.process_article(make_article())
    result = service.process_article(make_article(text="<p>&nbsp;</p>"))
    assert result.action == "deleted"
    assert not repo.article_exists("a1")


def test_embedding_failure_leaves_existing_vectors_untouched(make_service, repo):
    service, _ = make_service()
    service.process_article(make_article())
    before = repo.count_article_points("a1")

    service2, sn = make_service([make_article()], embedder=FakeEmbedder(fail_on="VPN"))
    result = service2.sync_article("a1")
    assert result.action == "failed"
    assert "embedding failed" in result.error
    assert repo.count_article_points("a1") == before  # embed happens before delete


def test_embedding_dimension_mismatch_is_reported(make_service, repo):
    service, _ = make_service([make_article()], embedder=FakeEmbedder(wrong_dim=True))
    result = service.sync_article("a1")
    assert result.action == "failed"
    assert "EMBEDDING_DIMENSION=8" in result.error
    assert repo.count_article_points("a1") == 0


def test_batch_isolates_failures_per_article(make_service, repo):
    articles = [
        make_article("s1", "KB001"),
        make_article("s2", "KB002", text="<p>" + "BOOM trigger. " * 30 + "</p>"),
        make_article("s3", "KB003"),
    ]
    service, _ = make_service(articles, embedder=FakeEmbedder(fail_on="BOOM"))
    summary = service.run_sync(full=True)
    assert summary.status == "completed_with_errors"
    assert (summary.processed, summary.created, summary.failed) == (3, 2, 1)
    assert summary.failures[0].number == "KB002"
    assert repo.article_exists("s1") and repo.article_exists("s3")
    assert not repo.article_exists("s2")


def test_batch_summary_counts(make_service, repo):
    existing = make_article("s2", "KB002")
    service, sn = make_service([existing])
    service.process_article(existing)  # s2 already indexed
    service.process_article(make_article("s4", "KB004"))  # s4 indexed, about to be retired

    sn.articles = {
        "s1": make_article("s1", "KB001"),  # new
        "s2": make_article("s2", "KB002", text="<p>changed</p>"),  # updated
        "s4": make_article("s4", "KB004", workflow_state="retired", published=False),  # removed
    }
    summary = service.run_sync(full=True)
    assert summary.model_dump(exclude={"since", "failures"}) == {
        "status": "completed",
        "processed": 3,
        "created": 1,
        "updated": 1,
        "deleted": 1,
        "skipped": 0,
        "failed": 0,
    }


def test_parse_failures_from_servicenow_are_counted(make_service):
    from app.services.servicenow import FetchFailure

    service, sn = make_service([make_article()])
    sn.parse_failures = [FetchFailure("bad1", "Article record has no sys_id")]
    summary = service.run_sync(full=True)
    assert summary.failed == 1 and summary.created == 1


def test_single_sync_of_missing_article_removes_vectors(make_service, repo):
    service, sn = make_service([make_article()])
    service.sync_article("a1")
    assert repo.article_exists("a1")
    sn.articles.clear()  # deleted in ServiceNow
    result = service.sync_article("a1")
    assert result.action == "deleted"
    assert not repo.article_exists("a1")


def test_watermark_advances_only_on_clean_runs(make_service, tmp_path):
    store = SyncStateStore(tmp_path / "state.json")
    service, sn = make_service([make_article()], state_store=store)

    summary = service.run_sync()  # no watermark yet -> initial lookback
    assert summary.failed == 0
    saved = store.load()
    assert saved is not None and datetime.now(UTC) - saved < timedelta(minutes=5)

    # Explicit window must not move the watermark.
    service.run_sync(since=datetime(2020, 1, 1))
    assert store.load() == saved

    # Failing run must not move it either.
    failing, _ = make_service(
        [make_article()], embedder=FakeEmbedder(fail_on="VPN"), state_store=store
    )
    assert failing.run_sync().failed == 1
    assert store.load() == saved


def test_sync_uses_saved_watermark(make_service, tmp_path):
    store = SyncStateStore(tmp_path / "state.json")
    mark = datetime(2026, 9, 1, tzinfo=UTC)
    store.save(mark)
    service, _ = make_service([make_article()], state_store=store)
    assert service.run_sync().since == mark


def test_state_store_tolerates_corruption(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json")
    assert SyncStateStore(path).load() is None


@pytest.mark.parametrize(
    "html,expected",
    [
        ("<p>Hello&nbsp;<b>world</b></p><script>alert(1)</script>", "Hello world"),
        ("<ul><li>one</li><li>two</li></ul>", "- one\n- two"),
        ("  plain   text \n\n\n\n here ", "plain text\n\nhere"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalizer(html, expected):
    from app.services.normalizer import normalize_content

    assert normalize_content(html) == expected


def test_sections_are_stored_per_chunk_and_replaced_on_update(make_service, repo):
    html = (
        "<p><strong>Problem:</strong> " + "cannot sign in. " * 30 + "</p>"
        "<p><strong>Resolution:</strong> " + "reset the password. " * 30 + "</p>"
    )
    service, _ = make_service()
    result = service.process_article(make_article(text=html))
    points = repo._client.scroll("test_kb", limit=100)[0]
    assert len(points) == result.chunks
    assert {p.payload["section"] for p in points} == {"Problem", "Resolution"}
    assert sorted(p.payload["chunk_index"] for p in points) == list(range(result.chunks))

    service.process_article(make_article(text="<p>Now a plain article.</p>"))
    points = repo._client.scroll("test_kb", limit=100)[0]
    assert [p.payload["section"] for p in points] == ["Body"]  # old sections are gone
