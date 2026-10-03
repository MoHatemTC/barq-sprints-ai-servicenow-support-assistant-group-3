import pytest
from pydantic import ValidationError

from tests.conftest import make_settings


def test_valid_settings_and_defaults():
    s = make_settings()
    assert s.chunk_size == 500 and s.chunk_overlap == 50
    assert s.published_states == ["published"]
    assert s.qdrant_api_key is None


def test_empty_optional_values_are_unset():
    s = make_settings(qdrant_api_key="", webhook_secret="", qdrant_vector_name="")
    assert s.qdrant_api_key is None and s.webhook_secret is None and s.qdrant_vector_name is None


def test_secrets_are_not_in_repr():
    assert "not-a-real-password" not in repr(make_settings())


@pytest.mark.parametrize(
    "override",
    [
        {"chunk_overlap": 500},
        {"embedding_dimension": 0},
        {"service_now_url": "not-a-url"},
        {"service_now_password": " "},
        {"service_now_published_states": "published^ORactive=false"},
        {"log_level": "LOUD"},
    ],
)
def test_invalid_settings_rejected(override):
    with pytest.raises(ValidationError):
        make_settings(**override)


def test_url_trailing_slash_trimmed():
    assert make_settings(service_now_url="https://x.service-now.com/").service_now_url == (
        "https://x.service-now.com"
    )
