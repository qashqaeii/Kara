"""Custom exceptions for Kara integration."""


class KaraError(Exception):
    """Base exception for Kara-related errors."""


class LoginExpiredError(KaraError):
    """Session or cookie has expired."""


class KaraNetworkError(KaraError):
    """Network or HTTP communication failure."""


class InvalidResponseError(KaraError):
    """Server returned an unexpected or invalid payload."""


class AuthenticationError(KaraError):
    """Login credentials are missing or rejected."""


class ReportNotFoundError(KaraError):
    """Requested report key is not registered."""
