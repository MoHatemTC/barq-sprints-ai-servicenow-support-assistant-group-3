"""Domain exceptions. Every failure the service understands maps to one of these."""


class KBSyncError(Exception):
    """Base class for all expected errors raised by this service."""


class ConfigurationError(KBSyncError):
    """Invalid or inconsistent configuration (e.g. Qdrant vector size mismatch)."""


class ServiceNowError(KBSyncError):
    """Generic ServiceNow failure (HTTP error, timeout, transport problem)."""


class ServiceNowAuthError(ServiceNowError):
    """ServiceNow rejected the credentials (HTTP 401/403)."""


class ServiceNowNotFoundError(ServiceNowError):
    """The requested record does not exist (or is not visible to the integration user)."""


class ServiceNowResponseError(ServiceNowError):
    """ServiceNow returned an empty or malformed response."""


class EmbeddingError(KBSyncError):
    """The embedding provider failed."""


class EmbeddingDimensionError(EmbeddingError):
    """A vector's dimension does not match the configured EMBEDDING_DIMENSION."""


class QdrantError(KBSyncError):
    """A Qdrant operation failed."""
