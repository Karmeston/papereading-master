class FinalsAgentError(Exception):
    """Base exception for expected project errors."""


class ConfigurationError(FinalsAgentError):
    """Raised when required runtime configuration is missing or invalid."""


class MaterialNotFoundError(FinalsAgentError):
    """Raised when a requested paper material cannot be found."""


class UnsupportedMaterialTypeError(FinalsAgentError):
    """Raised when a file type is not supported by the current scaffold."""


class IngestInputError(FinalsAgentError):
    """Raised when a material ingest request is invalid."""


class RepositoryIndexError(FinalsAgentError):
    """Raised when the local material index cannot be read or written."""


class ToolInputError(FinalsAgentError):
    """Raised when a LangChain tool receives invalid input."""


class ExternalSearchError(FinalsAgentError):
    """Raised when an external paper search provider cannot return results."""


class VisionProcessingError(FinalsAgentError):
    """Raised when a vision artifact interpreter cannot process an image."""
