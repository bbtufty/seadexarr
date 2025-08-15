"""
Custom exceptions for SeaDexArr.
"""

import json
from typing import Any


class SeaDexArrError(Exception):
    """Base exception for all SeaDexArr errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(SeaDexArrError):
    """Raised when there are configuration issues."""

    pass


class APIError(SeaDexArrError):
    """Raised when API calls fail."""

    def __init__(
        self, message: str, status_code: int | None = None, response: str | None = None
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class AuthenticationError(APIError):
    """Raised when authentication fails."""

    pass


class RateLimitError(APIError):
    """Raised when API rate limits are exceeded."""

    pass


class ServiceUnavailableError(APIError):
    """Raised when a service is unavailable."""

    pass


class DataMappingError(SeaDexArrError):
    """Raised when data mapping/transformation fails."""

    pass


class FilterError(SeaDexArrError):
    """Raised when filtering operations fail."""

    pass


def parse_api_error(response_text: str, status_code: int) -> APIError:
    """Parse API error response and return appropriate exception."""
    try:
        error_data = json.loads(response_text)
        message = error_data.get("message", f"API error (HTTP {status_code})")

        if status_code == 401:
            return AuthenticationError(message, status_code, response_text)
        elif status_code == 429:
            return RateLimitError(message, status_code, response_text)
        elif status_code >= 500:
            return ServiceUnavailableError(message, status_code, response_text)
        else:
            return APIError(message, status_code, response_text)

    except (json.JSONDecodeError, KeyError):
        # Fallback for non-JSON responses or missing message field
        return APIError(f"API error (HTTP {status_code})", status_code, response_text)
