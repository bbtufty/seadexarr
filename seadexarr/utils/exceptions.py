"""
Enhanced exception hierarchy for SeaDexArr.

Comprehensive exception system with context management, error categorization,
troubleshooting suggestions, and integration with structured logging.
"""

import json
import time
from enum import Enum
from typing import Any

from .logging import get_logger

logger = get_logger(__name__)


class ErrorCategory(Enum):
    """Categories for error classification."""

    USER_ERROR = "user_error"
    CONFIGURATION_ERROR = "configuration_error"
    NETWORK_ERROR = "network_error"
    API_ERROR = "api_error"
    DATA_ERROR = "data_error"
    SYSTEM_ERROR = "system_error"
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    SECURITY_ERROR = "security_error"
    PERFORMANCE_ERROR = "performance_error"


class ErrorSeverity(Enum):
    """Severity levels for errors."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SeaDexArrError(Exception):
    """
    Enhanced base exception for all SeaDexArr errors.

    Provides comprehensive error context, categorization, and troubleshooting guidance.
    """

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        category: ErrorCategory = ErrorCategory.SYSTEM_ERROR,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        correlation_id: str | None = None,
        user_message: str | None = None,
        troubleshooting_hints: list[str] | None = None,
        retryable: bool = False,
        **context: Any,
    ):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.category = category
        self.severity = severity
        self.correlation_id = correlation_id
        self.user_message = user_message or message
        self.troubleshooting_hints = troubleshooting_hints or []
        self.retryable = retryable
        self.context = context
        self.timestamp = time.time()

        # Log the error creation
        self._log_error()

    def _log_error(self) -> None:
        """Log error creation with full context."""
        logger.error(
            f"Exception created: {self.__class__.__name__}",
            error=self.message,
            category=self.category.value,
            severity=self.severity.value,
            retryable=self.retryable,
            correlation_id=self.correlation_id,
            **self.details,
            **self.context,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary representation."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "user_message": self.user_message,
            "category": self.category.value,
            "severity": self.severity.value,
            "retryable": self.retryable,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "details": self.details,
            "troubleshooting_hints": self.troubleshooting_hints,
            "context": self.context,
        }

    def with_context(self, **context: Any) -> "SeaDexArrError":
        """Add additional context to the error."""
        self.context.update(context)
        return self


class ConfigurationError(SeaDexArrError):
    """Raised when there are configuration issues."""

    def __init__(
        self,
        message: str,
        config_key: str | None = None,
        expected_value: str | None = None,
        actual_value: str | None = None,
        **kwargs,
    ):
        hints = [
            "Check your configuration file (.env) for missing or incorrect values",
            "Verify environment variables are properly set",
            "Run 'seadexarr config-validate' to diagnose configuration issues",
        ]

        if config_key:
            hints.append(f"Ensure '{config_key}' is properly configured")
            kwargs.setdefault("details", {})["config_key"] = config_key

        if expected_value:
            kwargs.setdefault("details", {})["expected_value"] = expected_value

        if actual_value:
            kwargs.setdefault("details", {})["actual_value"] = actual_value

        super().__init__(
            message,
            category=ErrorCategory.CONFIGURATION_ERROR,
            troubleshooting_hints=hints,
            retryable=False,
            **kwargs,
        )


class APIError(SeaDexArrError):
    """Enhanced API error with detailed context and retry logic."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: str | None = None,
        service: str | None = None,
        endpoint: str | None = None,
        request_id: str | None = None,
        **kwargs,
    ):
        details = kwargs.setdefault("details", {})
        details.update(
            {
                "status_code": status_code,
                "response": response,
                "service": service,
                "endpoint": endpoint,
                "request_id": request_id,
            }
        )

        # Determine if retryable based on status code
        retryable = self._is_retryable_status(status_code)

        hints = self._generate_troubleshooting_hints(status_code, service)

        super().__init__(
            message,
            category=ErrorCategory.API_ERROR,
            severity=self._determine_severity(status_code),
            troubleshooting_hints=hints,
            retryable=retryable,
            **kwargs,
        )

    @staticmethod
    def _is_retryable_status(status_code: int | None) -> bool:
        """Determine if an HTTP status code indicates a retryable error."""
        if not status_code:
            return True

        # Server errors (5xx) and rate limiting (429) are retryable
        return status_code >= 500 or status_code == 429

    @staticmethod
    def _determine_severity(status_code: int | None) -> ErrorSeverity:
        """Determine error severity based on status code."""
        if not status_code:
            return ErrorSeverity.MEDIUM

        if status_code >= 500:
            return ErrorSeverity.HIGH
        elif status_code == 429:
            return ErrorSeverity.MEDIUM
        elif status_code >= 400:
            return ErrorSeverity.LOW
        else:
            return ErrorSeverity.MEDIUM

    @staticmethod
    def _generate_troubleshooting_hints(
        status_code: int | None, service: str | None
    ) -> list[str]:
        """Generate troubleshooting hints based on status code and service."""
        hints = []

        if status_code == 401:
            hints.extend(
                [
                    "Check your API credentials and ensure they're not expired",
                    "Verify the API key has the required permissions",
                    (
                        f"Re-authenticate with {service} if using token-based auth"
                        if service
                        else "Re-authenticate with the service"
                    ),
                ]
            )
        elif status_code == 403:
            hints.extend(
                [
                    "Your API key may not have sufficient permissions",
                    "Check if your account has access to the requested resource",
                    "Contact the service administrator if permissions seem correct",
                ]
            )
        elif status_code == 404:
            hints.extend(
                [
                    "The requested resource was not found",
                    "Check if the URL/endpoint is correct",
                    "Verify the resource ID exists in the service",
                ]
            )
        elif status_code == 429:
            hints.extend(
                [
                    "API rate limit exceeded - the system will automatically retry",
                    "Consider reducing the frequency of API calls",
                    "Check if you have a higher rate limit available",
                ]
            )
        elif status_code and status_code >= 500:
            hints.extend(
                [
                    (
                        f"{service} is experiencing server issues"
                        if service
                        else "The service is experiencing server issues"
                    ),
                    "This is likely a temporary issue that will resolve automatically",
                    "Check the service status page if available",
                ]
            )
        else:
            hints.extend(
                [
                    "Check network connectivity to the service",
                    "Verify the service URL is correct and accessible",
                    "Check firewall and proxy settings",
                ]
            )

        return hints


class AuthenticationError(APIError):
    """Raised when authentication fails."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            status_code=401,
            category=ErrorCategory.SECURITY_ERROR,
            severity=ErrorSeverity.HIGH,
            **kwargs,
        )


class AuthorizationError(APIError):
    """Raised when authorization fails (403)."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            status_code=403,
            category=ErrorCategory.SECURITY_ERROR,
            severity=ErrorSeverity.HIGH,
            **kwargs,
        )


class RateLimitError(APIError):
    """Raised when API rate limits are exceeded."""

    def __init__(
        self,
        message: str,
        retry_after: int | None = None,
        remaining_requests: int | None = None,
        **kwargs,
    ):
        details = kwargs.setdefault("details", {})
        details.update(
            {
                "retry_after": retry_after,
                "remaining_requests": remaining_requests,
            }
        )

        super().__init__(message, status_code=429, retryable=True, **kwargs)


class ServiceUnavailableError(APIError):
    """Raised when a service is unavailable."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.EXTERNAL_SERVICE_ERROR,
            severity=ErrorSeverity.HIGH,
            retryable=True,
            **kwargs,
        )


class NetworkError(SeaDexArrError):
    """Raised when network connectivity issues occur."""

    def __init__(
        self,
        message: str,
        host: str | None = None,
        port: int | None = None,
        timeout: float | None = None,
        **kwargs,
    ):
        details = kwargs.setdefault("details", {})
        details.update(
            {
                "host": host,
                "port": port,
                "timeout": timeout,
            }
        )

        hints = [
            "Check your internet connection",
            "Verify the service URL is correct and accessible",
            "Check firewall and proxy settings",
            "Try increasing the timeout value if the service is slow",
        ]

        if host:
            hints.append(f"Verify that {host} is reachable from your network")

        super().__init__(
            message,
            category=ErrorCategory.NETWORK_ERROR,
            severity=ErrorSeverity.MEDIUM,
            troubleshooting_hints=hints,
            retryable=True,
            **kwargs,
        )


class DataMappingError(SeaDexArrError):
    """Raised when data mapping/transformation fails."""

    def __init__(
        self,
        message: str,
        source_data: dict[str, Any] | None = None,
        expected_format: str | None = None,
        mapping_rule: str | None = None,
        **kwargs,
    ):
        details = kwargs.setdefault("details", {})
        details.update(
            {
                "source_data": source_data,
                "expected_format": expected_format,
                "mapping_rule": mapping_rule,
            }
        )

        hints = [
            "Check if the source data structure has changed",
            "Verify the mapping configuration is correct",
            "Check for missing required fields in the source data",
        ]

        super().__init__(
            message,
            category=ErrorCategory.DATA_ERROR,
            troubleshooting_hints=hints,
            retryable=False,
            **kwargs,
        )


class FilterError(SeaDexArrError):
    """Raised when filtering operations fail."""

    def __init__(
        self,
        message: str,
        filter_expression: str | None = None,
        filter_type: str | None = None,
        **kwargs,
    ):
        details = kwargs.setdefault("details", {})
        details.update(
            {
                "filter_expression": filter_expression,
                "filter_type": filter_type,
            }
        )

        hints = [
            "Check the filter expression syntax",
            "Verify the filter criteria are valid for the data type",
            "Ensure required fields exist in the data being filtered",
        ]

        super().__init__(
            message,
            category=ErrorCategory.DATA_ERROR,
            troubleshooting_hints=hints,
            retryable=False,
            **kwargs,
        )


class ValidationError(SeaDexArrError):
    """Raised when data validation fails."""

    def __init__(
        self,
        message: str,
        field_name: str | None = None,
        field_value: Any | None = None,
        validation_rule: str | None = None,
        **kwargs,
    ):
        details = kwargs.setdefault("details", {})
        details.update(
            {
                "field_name": field_name,
                "field_value": field_value,
                "validation_rule": validation_rule,
            }
        )

        hints = [
            "Check the input data format and values",
            "Verify all required fields are provided",
            "Ensure data types match the expected format",
        ]

        if field_name:
            hints.append(f"Check the value provided for field '{field_name}'")

        super().__init__(
            message,
            category=ErrorCategory.USER_ERROR,
            troubleshooting_hints=hints,
            retryable=False,
            **kwargs,
        )


class TimeoutError(NetworkError):
    """Raised when operations timeout."""

    def __init__(
        self,
        message: str,
        timeout_duration: float | None = None,
        operation: str | None = None,
        **kwargs,
    ):
        details = kwargs.setdefault("details", {})
        details.update(
            {
                "timeout_duration": timeout_duration,
                "operation": operation,
            }
        )

        hints = [
            "Try increasing the timeout value in configuration",
            "Check if the target service is responding slowly",
            "Verify network connectivity is stable",
        ]

        if operation:
            hints.append(f"The '{operation}' operation timed out")

        super().__init__(
            message,
            category=ErrorCategory.PERFORMANCE_ERROR,
            severity=ErrorSeverity.MEDIUM,
            **kwargs,
        )


class CircuitBreakerError(SeaDexArrError):
    """Raised when circuit breaker is open."""

    def __init__(
        self,
        message: str,
        service: str | None = None,
        failure_count: int | None = None,
        next_attempt_time: float | None = None,
        **kwargs,
    ):
        details = kwargs.setdefault("details", {})
        details.update(
            {
                "service": service,
                "failure_count": failure_count,
                "next_attempt_time": next_attempt_time,
            }
        )

        hints = [
            "The service is temporarily unavailable due to repeated failures",
            "Wait for the circuit breaker to reset automatically",
            "Check the service health and fix underlying issues",
        ]

        if service:
            hints.append(f"Service '{service}' is currently circuit-broken")

        super().__init__(
            message,
            category=ErrorCategory.EXTERNAL_SERVICE_ERROR,
            severity=ErrorSeverity.HIGH,
            troubleshooting_hints=hints,
            retryable=True,
            **kwargs,
        )


class RetryExhaustedError(SeaDexArrError):
    """Raised when all retry attempts are exhausted."""

    def __init__(
        self,
        message: str,
        attempt_count: int | None = None,
        last_error: Exception | None = None,
        operation: str | None = None,
        **kwargs,
    ):
        details = kwargs.setdefault("details", {})
        details.update(
            {
                "attempt_count": attempt_count,
                "last_error": str(last_error) if last_error else None,
                "last_error_type": type(last_error).__name__ if last_error else None,
                "operation": operation,
            }
        )

        hints = [
            "All retry attempts have been exhausted",
            "Check the underlying cause of the repeated failures",
            "Consider increasing retry limits or wait times if appropriate",
        ]

        if operation:
            hints.append(
                f"Operation '{operation}' failed after {attempt_count} attempts"
            )

        super().__init__(
            message,
            category=ErrorCategory.SYSTEM_ERROR,
            severity=ErrorSeverity.HIGH,
            troubleshooting_hints=hints,
            retryable=False,
            **kwargs,
        )


def parse_api_error(
    response_text: str,
    status_code: int,
    service: str | None = None,
    endpoint: str | None = None,
) -> APIError:
    """Parse API error response and return appropriate exception with enhanced context."""
    try:
        error_data = json.loads(response_text)
        message = error_data.get("message", f"API error (HTTP {status_code})")
        request_id = error_data.get("request_id") or error_data.get("requestId")

        # Create appropriate error type based on status code
        if status_code == 401:
            return AuthenticationError(
                message,
                status_code=status_code,
                response=response_text,
                service=service,
                endpoint=endpoint,
                request_id=request_id,
                details=error_data,
            )
        elif status_code == 403:
            return AuthorizationError(
                message,
                status_code=status_code,
                response=response_text,
                service=service,
                endpoint=endpoint,
                request_id=request_id,
                details=error_data,
            )
        elif status_code == 429:
            retry_after = error_data.get("retry_after")
            remaining = error_data.get("remaining_requests")
            return RateLimitError(
                message,
                status_code=status_code,
                retry_after=retry_after,
                remaining_requests=remaining,
                response=response_text,
                service=service,
                endpoint=endpoint,
                request_id=request_id,
                details=error_data,
            )
        elif status_code >= 500:
            return ServiceUnavailableError(
                message,
                status_code=status_code,
                response=response_text,
                service=service,
                endpoint=endpoint,
                request_id=request_id,
                details=error_data,
            )
        else:
            return APIError(
                message,
                status_code=status_code,
                response=response_text,
                service=service,
                endpoint=endpoint,
                request_id=request_id,
                details=error_data,
            )

    except (json.JSONDecodeError, KeyError):
        # Fallback for non-JSON responses or missing message field
        return APIError(
            f"API error (HTTP {status_code})",
            status_code=status_code,
            response=response_text,
            service=service,
            endpoint=endpoint,
        )


def create_user_friendly_error(
    error: Exception, context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Create a user-friendly error representation."""
    if isinstance(error, SeaDexArrError):
        error_dict = error.to_dict()
    else:
        error_dict = {
            "error_type": type(error).__name__,
            "message": str(error),
            "user_message": str(error),
            "category": ErrorCategory.SYSTEM_ERROR.value,
            "severity": ErrorSeverity.MEDIUM.value,
            "retryable": False,
            "troubleshooting_hints": ["Check the application logs for more details"],
            "context": context or {},
        }

    return {
        "success": False,
        "error": error_dict,
        "timestamp": time.time(),
    }
