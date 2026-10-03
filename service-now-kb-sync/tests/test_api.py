import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import FakeEmbedder, make_article, make_container


@pytest.fixture
def build(make_service, repo):
    def _build(articles=(), embedder=None, **settings):
        service, sn = make_service(list(articles), embedder=embedder)
        return TestClient(create_app(make_container(service, sn, repo, **settings))), sn

    return _build


def test_health(build):
    client, _ = build()
    assert client.get("/health").json() == {"status": "ok"}


def test_deep_health_ok_and_degraded(build, repo):
    client, sn = build()
    body = client.get("/health?deep=true").json()
    assert body["status"] == "ok" and body["dependencies"] == {"qdrant": "ok", "servicenow": "ok"}

    sn.ping = lambda: (_ for _ in ()).throw(RuntimeError("down"))
    response = client.get("/health?deep=true")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_sync_one(build, repo):
    client, _ = build([make_article()])
    response = client.post("/kb/sync/a1")
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "success" and body["sys_id"] == "a1" and body["chunks"] > 0
    assert repo.article_exists("a1")


def test_sync_one_failure_returns_502(build):
    client, _ = build([make_article()], embedder=FakeEmbedder(fail_on="VPN"))
    response = client.post("/kb/sync/a1")
    assert response.status_code == 502
    assert response.json()["status"] == "failed"


def test_sync_one_rejects_bad_sys_id(build):
    client, _ = build()
    assert client.post("/kb/sync/bad id!").status_code == 422


def test_sync_all_with_and_without_body(build, repo, tmp_path):
    client, _ = build(
        [make_article("s1", "KB1"), make_article("s2", "KB2")],
        sync_state_path=str(tmp_path / "s.json"),
    )
    body = client.post("/kb/sync", json={"full": True}).json()
    assert body["status"] == "completed" and body["created"] == 2 and body["failed"] == 0
    assert client.post("/kb/sync").json()["updated"] == 2  # body is optional


def test_api_token_protects_sync_endpoints(build):
    client, _ = build([make_article()], api_auth_token="s3cret-token")
    assert client.post("/kb/sync/a1").status_code == 401
    assert client.post("/kb/sync/a1", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.post("/kb/sync/a1", headers={"X-API-Key": "s3cret-token"}).status_code == 200
    assert client.get("/health").status_code == 200  # health stays open


def test_webhook_disabled_without_secret(build):
    client, _ = build()
    assert client.post("/kb/events", json={"sys_id": "a1"}).status_code == 503


def test_webhook_requires_secret_and_syncs(build, repo):
    client, _ = build([make_article()], webhook_secret="hook-secret")
    assert client.post("/kb/events", json={"sys_id": "a1"}).status_code == 401
    bad = client.post("/kb/events", json={"sys_id": "a1"}, headers={"X-Webhook-Secret": "nope"})
    assert bad.status_code == 401
    ok = client.post(
        "/kb/events", json={"sys_id": "a1"}, headers={"X-Webhook-Secret": "hook-secret"}
    )
    assert ok.status_code == 202
    assert repo.article_exists("a1")  # background task has run by the time TestClient returns


def test_webhook_validates_payload(build):
    client, _ = build(webhook_secret="hook-secret")
    response = client.post(
        "/kb/events", json={"sys_id": "../x"}, headers={"X-Webhook-Secret": "hook-secret"}
    )
    assert response.status_code == 422
