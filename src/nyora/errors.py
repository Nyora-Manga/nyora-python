"""Nyora SDK exceptions.

Defines the exception hierarchy raised across the SDK. :class:`NyoraError` is
the common base; helper discovery, helper launch, and helper HTTP failures each
have a dedicated subclass so callers can catch them selectively.
"""


class NyoraError(Exception):
    """Base exception for Nyora SDK failures."""


class HelperNotFoundError(NyoraError):
    """Raised when no running helper can be discovered."""


class HelperLaunchError(NyoraError):
    """Raised when a managed helper process fails to start."""


class NyoraHTTPError(NyoraError):
    """Raised when the helper returns a non-successful HTTP response.

    Attributes:
        status_code: The HTTP status code returned by the helper.
        body: The raw response body, when available.
    """

    def __init__(self, status_code: int, message: str, *, body: str = "") -> None:
        """Initialize the error.

        Args:
            status_code: The HTTP status code (>= 400).
            message: A human-readable error message.
            body: The raw response body, when available.
        """
        self.status_code = status_code
        self.body = body
        super().__init__(f"Nyora helper returned HTTP {status_code}: {message}")
