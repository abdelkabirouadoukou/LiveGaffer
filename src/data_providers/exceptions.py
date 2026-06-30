"""
Custom exceptions for the data provider layer.

Using a dedicated hierarchy (instead of letting raw httpx/JSON exceptions
bubble up) lets calling code (services layer, Streamlit UI) catch precise
failure modes and react appropriately — e.g. show "rate limit reached,
try again in a minute" instead of a raw stack trace.
"""

from __future__ import annotations


class DataProviderError(Exception):
    """Base class for all data-provider-related errors."""


class ProviderConnectionError(DataProviderError):
    """Raised when the underlying HTTP request fails (network, timeout, DNS)."""


class ProviderAuthenticationError(DataProviderError):
    """Raised on 401/403 responses — invalid or missing API key."""


class ProviderRateLimitError(DataProviderError):
    """Raised on 429 responses — free-tier quota exceeded."""

    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ProviderResponseError(DataProviderError):
    """Raised when the API returns a non-2xx status not covered above."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class ProviderDataValidationError(DataProviderError):
    """Raised when the API response cannot be parsed into our Pydantic schemas."""


class FixtureNotFoundError(DataProviderError):
    """Raised when a requested fixture ID does not exist or has no data."""
