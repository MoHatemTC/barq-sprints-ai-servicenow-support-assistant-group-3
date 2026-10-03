import math
import re
from typing import Any

import httpx

from .settings import Settings

_PASSWORD_CHANGE_PATTERN = re.compile(
    r"(\bpassword\b\s+from\s+)([^\s,;]+)(\s+to\s+)([^\s,;]+)",
    re.IGNORECASE,
)

_CREDENTIAL_ASSIGNMENT_PATTERN = re.compile(
    r"""(?ix)
    (\b(?:password|passwd|passcode|secret|token|api[\s_-]?key|access[\s_-]?token)\b
    \s*(?::|=)\s*)
    (?:"[^"]*"|'[^']*'|[^\s,;]+)
    """
)

_NATURAL_LANGUAGE_CREDENTIAL_PATTERN = re.compile(
    r"""(?ix)
    (\b(?:password|passwd|passcode|secret|token|api[\s_-]?key|access[\s_-]?token)\b
    \s+is\s+)
    (?:"[^"]*"|'[^']*'|[^\s,;]+)
    """
)

_CLASSIFIER_RESPONSE_KEYS = {"contains_secret", "true_probability"}
_CLASSIFIER_AUTH_SCHEME = "Bearer"

def _redact_pattern(pattern: re.Pattern[str], text: str) -> str:
    return pattern.sub(lambda match: f"{match.group(1)}[REDACTED]", text)


def _pre_redact_known_formats(text: str) -> str:
    text = _PASSWORD_CHANGE_PATTERN.sub(
        r"\1[REDACTED]\3[REDACTED]",
        text,
    )
    return _redact_pattern(_CREDENTIAL_ASSIGNMENT_PATTERN, text)


def _redact_additional_labeled_values(text: str) -> str:
    return _redact_pattern(_NATURAL_LANGUAGE_CREDENTIAL_PATTERN, text)


def _validate_classifier_result(payload: Any) -> tuple[bool, float]:
    if (
        not isinstance(payload, dict)
        or set(payload) != _CLASSIFIER_RESPONSE_KEYS
        or not isinstance(payload["contains_secret"], bool)
        or isinstance(payload["true_probability"], bool)
        or not isinstance(payload["true_probability"], (int, float))
        or not math.isfinite(payload["true_probability"])
        or not 0.0 <= payload["true_probability"] <= 1.0
    ):
        raise RuntimeError("Password classifier returned an invalid response")
    true_probability = float(payload["true_probability"])
    if payload["contains_secret"] != (true_probability >= 0.5):
        raise RuntimeError("Password classifier returned inconsistent scores")
    return payload["contains_secret"], true_probability


def _classify_with_local_model(text: str, settings: Settings) -> bool:
    base_url = settings.password_classifier_base_url.rstrip("/")
    api_key = settings.password_classifier_api_key
    if not base_url:
        raise RuntimeError("PASSWORD_CLASSIFIER_BASE_URL must be configured")
    if not api_key:
        raise RuntimeError("PASSWORD_CLASSIFIER_API_KEY must be configured")

    response = httpx.post(
        f"{base_url}/classify",
        json={"text": text},
        headers={"Authorization": f"{_CLASSIFIER_AUTH_SCHEME} {api_key}"},
        timeout=settings.password_classifier_timeout_seconds,
    )
    response.raise_for_status()
    contains_secret, _ = _validate_classifier_result(response.json())
    return contains_secret


def classify_password_presence(text: str, settings: Settings) -> bool:
    """Classify text using a local next-token-logit scoring service."""
    return _classify_with_local_model(text, settings)


def sanitize_text_fields(
    fields: dict[str, str],
    settings: Settings,
) -> dict[str, str]:
    """Mask known credential formats and fail closed on unlocated secrets."""
    if not fields:
        return {}

    result = {
        key: _pre_redact_known_formats(value)
        for key, value in fields.items()
    }
    classifier_input = "\n".join(
        f"{key}: {value}" for key, value in result.items()
    )
    if not classify_password_presence(classifier_input, settings):
        return result

    additional_redactions = {
        key: _redact_additional_labeled_values(value)
        for key, value in result.items()
    }
    if additional_redactions == result:
        raise RuntimeError(
            "Password classifier detected a credential that local redaction "
            "patterns could not locate"
        )

    verification_input = "\n".join(
        f"{key}: {value}" for key, value in additional_redactions.items()
    )
    if classify_password_presence(verification_input, settings):
        raise RuntimeError(
            "Password classifier still detects a credential after local redaction"
        )
    return additional_redactions


def sanitize_chunk_fields(
    chunk: dict[str, Any],
    settings: Settings,
) -> None:
    """Sanitize chunk text and string metadata before external processing."""
    fields = {
        "text": chunk["text"],
        "section": chunk["section"],
        **{
            f"metadata.{key}": value
            for key, value in chunk["metadata"].items()
            if isinstance(value, str)
        },
    }
    sanitized = sanitize_text_fields(fields, settings)
    chunk["text"] = sanitized.pop("text")
    chunk["section"] = sanitized.pop("section")
    chunk["metadata"] = {
        key: sanitized[f"metadata.{key}"] if isinstance(value, str) else value
        for key, value in chunk["metadata"].items()
    }
