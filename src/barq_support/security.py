import hashlib
import hmac
import logging
import secrets

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


def compute_hmac_signature(raw_body: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 hex digest for the given raw body and secret."""
    return hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()


def verify_hmac_signature(
    raw_body: bytes,
    signature_header: str | None,
    secret: str,
) -> None:
    """
    Verify HMAC-SHA256 signature of raw request body using constant-time comparison.
    Signature arrives in header `X-Signature`.
    Raises HTTPException(401) on missing or invalid signature.
    """
    if not signature_header:
        logger.warning("Webhook request missing X-Signature header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Signature header",
        )

    if not secret:
        logger.error("SERVICENOW_WEBHOOK_SECRET is not configured")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook signing secret not configured",
        )

    expected_hex = compute_hmac_signature(raw_body, secret)

    provided = signature_header.strip()
    if provided.lower().startswith("sha256="):
        provided = provided[len("sha256="):].strip()

    if not secrets.compare_digest(provided.lower(), expected_hex.lower()):
        logger.warning("Webhook signature verification failed: invalid signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )

    logger.debug("Webhook HMAC signature verified successfully")
