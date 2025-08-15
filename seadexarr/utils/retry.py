"""
Enhanced retry logic utilities for SeaDexArr.

Comprehensive retry system with circuit breakers, exponential backoff with jitter,
sophisticated retry strategies, and integration with enhanced logging and exceptions.
"""

import asyncio
import builtins
import functools
import random
import time
from collections.abc import Callable
from enum import Enum
from typing import Any

from .exceptions import (
    CircuitBreakerError,
    NetworkError,
    RetryExhaustedError,
    TimeoutError,
)
from .logging import get_logger, operation_logger

logger = get_logger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 3,
        timeout: float = 30.0,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.timeout = timeout


class CircuitBreaker:
    """
    Circuit breaker implementation for preventing cascade failures.

    Tracks failure rates and automatically opens/closes circuit based on
    service health to prevent overwhelming failing services.
    """

    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.next_attempt_time = 0.0

    def can_execute(self) -> bool:
        """Check if the circuit breaker allows execution."""
        current_time = time.time()

        if self.state == CircuitBreakerState.CLOSED:
            return True
        elif self.state == CircuitBreakerState.OPEN:
            if current_time >= self.next_attempt_time:
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
                logger.info(
                    f"Circuit breaker {self.name} transitioning to HALF_OPEN",
                    circuit_breaker=self.name,
                    state=self.state.value,
                )
                return True
            return False
        else:  # HALF_OPEN
            return True

    def record_success(self) -> None:
        """Record a successful operation."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                logger.info(
                    f"Circuit breaker {self.name} recovered - transitioning to CLOSED",
                    circuit_breaker=self.name,
                    state=self.state.value,
                    success_count=self.success_count,
                )
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = max(0, self.failure_count - 1)

    def record_failure(self, error: Exception) -> None:
        """Record a failed operation."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitBreakerState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                self.state = CircuitBreakerState.OPEN
                self.next_attempt_time = time.time() + self.config.recovery_timeout
                logger.warning(
                    f"Circuit breaker {self.name} opened due to failures",
                    circuit_breaker=self.name,
                    state=self.state.value,
                    failure_count=self.failure_count,
                    next_attempt_time=self.next_attempt_time,
                )
        elif self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
            self.next_attempt_time = time.time() + self.config.recovery_timeout
            logger.warning(
                f"Circuit breaker {self.name} returned to OPEN after half-open failure",
                circuit_breaker=self.name,
                state=self.state.value,
            )


# Global circuit breaker registry
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str, config: CircuitBreakerConfig | None = None
) -> CircuitBreaker:
    """Get or create a circuit breaker for the given service."""
    if name not in _circuit_breakers:
        if config is None:
            config = CircuitBreakerConfig()
        _circuit_breakers[name] = CircuitBreaker(name, config)
    return _circuit_breakers[name]


def is_retryable_exception(exception: Exception) -> bool:
    """Determine if an exception should trigger a retry."""
    # Import here to avoid circular imports
    import httpx

    # Network-related errors are generally retryable
    if isinstance(
        exception,
        NetworkError | TimeoutError | ConnectionError | OSError,
    ):
        return True

    # HTTP client errors
    if isinstance(
        exception,
        httpx.TimeoutException
        | httpx.ConnectTimeout
        | httpx.ReadTimeout
        | httpx.WriteTimeout
        | httpx.NetworkError
        | httpx.RemoteProtocolError
        | httpx.ConnectError,
    ):
        return True

    # HTTP status errors (selective)
    if isinstance(exception, httpx.HTTPStatusError):
        # Retry on server errors (5xx) and rate limiting (429)
        return (
            exception.response.status_code >= 500
            or exception.response.status_code == 429
        )

    # Custom retryable exceptions
    from .exceptions import SeaDexArrError

    if isinstance(exception, SeaDexArrError):
        return exception.retryable

    return False


def calculate_backoff_with_jitter(
    attempt: int,
    base_wait: float = 1.0,
    max_wait: float = 60.0,
    multiplier: float = 2.0,
    jitter: bool = True,
) -> float:
    """Calculate exponential backoff with optional jitter."""
    wait_time = min(base_wait * (multiplier ** (attempt - 1)), max_wait)

    if jitter:
        # Add ±25% jitter to prevent thundering herd
        jitter_range = wait_time * 0.25
        wait_time += random.uniform(-jitter_range, jitter_range)

    return max(0.1, wait_time)  # Ensure minimum wait time


class EnhancedRetryConfig:
    """Enhanced configuration for retry behavior."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_wait: float = 1.0,
        max_wait: float = 60.0,
        multiplier: float = 2.0,
        jitter: bool = True,
        timeout: float | None = None,
        circuit_breaker: str | None = None,
        retry_on: set[type] | None = None,
        stop_on: set[type] | None = None,
    ):
        self.max_attempts = max_attempts
        self.base_wait = base_wait
        self.max_wait = max_wait
        self.multiplier = multiplier
        self.jitter = jitter
        self.timeout = timeout
        self.circuit_breaker = circuit_breaker
        self.retry_on = retry_on or set()
        self.stop_on = stop_on or set()


def with_enhanced_retry(
    config: EnhancedRetryConfig | None = None,
    operation_name: str | None = None,
    **legacy_kwargs,
):
    """
    Enhanced decorator for retry logic with circuit breakers and sophisticated backoff.

    Args:
        config: Enhanced retry configuration
        operation_name: Name of the operation for logging
        **legacy_kwargs: Backward compatibility with old parameters
    """
    # Handle legacy parameters for backward compatibility
    if config is None:
        config = EnhancedRetryConfig(
            max_attempts=legacy_kwargs.get("max_attempts", 3),
            base_wait=legacy_kwargs.get("wait_min", 1.0),
            max_wait=legacy_kwargs.get("wait_max", 60.0),
            multiplier=legacy_kwargs.get("multiplier", 2.0),
            jitter=legacy_kwargs.get("jitter", True),
            circuit_breaker=legacy_kwargs.get("circuit_breaker"),
            retry_on=set(legacy_kwargs.get("retry_exceptions", [])),
            stop_on=set(legacy_kwargs.get("stop_on_exceptions", [])),
        )

    def decorator(func: Callable) -> Callable:
        func_operation_name = operation_name or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            circuit_breaker = None
            if config.circuit_breaker:
                circuit_breaker = get_circuit_breaker(config.circuit_breaker)

            with operation_logger(f"retry_operation_{func_operation_name}"):
                for attempt in range(1, config.max_attempts + 1):
                    # Check circuit breaker
                    if circuit_breaker and not circuit_breaker.can_execute():
                        raise CircuitBreakerError(
                            f"Circuit breaker {config.circuit_breaker} is open",
                            service=config.circuit_breaker,
                            failure_count=circuit_breaker.failure_count,
                            next_attempt_time=circuit_breaker.next_attempt_time,
                        )

                    try:
                        if config.timeout:
                            result = await asyncio.wait_for(
                                func(*args, **kwargs), timeout=config.timeout
                            )
                        else:
                            result = await func(*args, **kwargs)

                        # Record success with circuit breaker
                        if circuit_breaker:
                            circuit_breaker.record_success()

                        if attempt > 1:
                            logger.info(
                                f"Operation {func_operation_name} succeeded after retry",
                                attempt=attempt,
                                total_attempts=config.max_attempts,
                            )

                        return result

                    except builtins.TimeoutError:
                        timeout_error = TimeoutError(
                            f"Operation {func_operation_name} timed out",
                            timeout_duration=config.timeout,
                            operation=func_operation_name,
                        )

                        if circuit_breaker:
                            circuit_breaker.record_failure(timeout_error)

                        if (
                            attempt == config.max_attempts
                            or not is_retryable_exception(timeout_error)
                        ):
                            raise RetryExhaustedError(
                                f"Operation {func_operation_name} failed after {attempt} attempts",
                                attempt_count=attempt,
                                last_error=timeout_error,
                                operation=func_operation_name,
                            )

                    except Exception as e:
                        if circuit_breaker:
                            circuit_breaker.record_failure(e)

                        # Check if we should stop retrying
                        if config.stop_on and type(e) in config.stop_on:
                            raise e

                        # Check if we should retry
                        should_retry = (
                            config.retry_on and type(e) in config.retry_on
                        ) or (not config.retry_on and is_retryable_exception(e))

                        if not should_retry or attempt == config.max_attempts:
                            raise RetryExhaustedError(
                                f"Operation {func_operation_name} failed after {attempt} attempts",
                                attempt_count=attempt,
                                last_error=e,
                                operation=func_operation_name,
                            )

                        # Calculate backoff time
                        wait_time = calculate_backoff_with_jitter(
                            attempt,
                            config.base_wait,
                            config.max_wait,
                            config.multiplier,
                            config.jitter,
                        )

                        logger.warning(
                            f"Operation {func_operation_name} failed, retrying in {wait_time:.2f}s",
                            attempt=attempt,
                            max_attempts=config.max_attempts,
                            wait_time=wait_time,
                            error=str(e),
                            error_type=type(e).__name__,
                        )

                        await asyncio.sleep(wait_time)

                # This should never be reached, but just in case
                raise RetryExhaustedError(
                    f"Operation {func_operation_name} exhausted all retry attempts",
                    attempt_count=config.max_attempts,
                    operation=func_operation_name,
                )

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            circuit_breaker = None
            if config.circuit_breaker:
                circuit_breaker = get_circuit_breaker(config.circuit_breaker)

            for attempt in range(1, config.max_attempts + 1):
                # Check circuit breaker
                if circuit_breaker and not circuit_breaker.can_execute():
                    raise CircuitBreakerError(
                        f"Circuit breaker {config.circuit_breaker} is open",
                        service=config.circuit_breaker,
                        failure_count=circuit_breaker.failure_count,
                        next_attempt_time=circuit_breaker.next_attempt_time,
                    )

                try:
                    result = func(*args, **kwargs)

                    # Record success with circuit breaker
                    if circuit_breaker:
                        circuit_breaker.record_success()

                    if attempt > 1:
                        logger.info(
                            f"Operation {func_operation_name} succeeded after retry",
                            attempt=attempt,
                            total_attempts=config.max_attempts,
                        )

                    return result

                except Exception as e:
                    if circuit_breaker:
                        circuit_breaker.record_failure(e)

                    # Check if we should stop retrying
                    if config.stop_on and type(e) in config.stop_on:
                        raise e

                    # Check if we should retry
                    should_retry = (config.retry_on and type(e) in config.retry_on) or (
                        not config.retry_on and is_retryable_exception(e)
                    )

                    if not should_retry or attempt == config.max_attempts:
                        raise RetryExhaustedError(
                            f"Operation {func_operation_name} failed after {attempt} attempts",
                            attempt_count=attempt,
                            last_error=e,
                            operation=func_operation_name,
                        )

                    # Calculate backoff time
                    wait_time = calculate_backoff_with_jitter(
                        attempt,
                        config.base_wait,
                        config.max_wait,
                        config.multiplier,
                        config.jitter,
                    )

                    logger.warning(
                        f"Operation {func_operation_name} failed, retrying in {wait_time:.2f}s",
                        attempt=attempt,
                        max_attempts=config.max_attempts,
                        wait_time=wait_time,
                        error=str(e),
                        error_type=type(e).__name__,
                    )

                    time.sleep(wait_time)

            # This should never be reached, but just in case
            raise RetryExhaustedError(
                f"Operation {func_operation_name} exhausted all retry attempts",
                attempt_count=config.max_attempts,
                operation=func_operation_name,
            )

        # Return appropriate wrapper based on function type

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# Backward compatibility functions
def with_retry(
    max_attempts: int = 3,
    wait_min: float = 1.0,
    wait_max: float = 10.0,
    retry_exceptions: tuple = (Exception,),
    stop_on_exceptions: tuple | None = None,
):
    """Legacy retry decorator for backward compatibility."""
    config = EnhancedRetryConfig(
        max_attempts=max_attempts,
        base_wait=wait_min,
        max_wait=wait_max,
        retry_on=set(retry_exceptions) if retry_exceptions else None,
        stop_on=set(stop_on_exceptions) if stop_on_exceptions else None,
    )

    return with_enhanced_retry(config)


def with_http_retry(max_attempts: int = 3):
    """Decorator specifically for HTTP requests with appropriate retry logic."""
    import httpx

    config = EnhancedRetryConfig(
        max_attempts=max_attempts,
        base_wait=1.0,
        max_wait=30.0,
        multiplier=2.0,
        jitter=True,
        retry_on={
            httpx.TimeoutException,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
        },
        stop_on={httpx.HTTPStatusError},  # Let API-specific logic handle these
    )

    return with_enhanced_retry(config, operation_name="http_request")


def with_api_retry(max_attempts: int = 3, service_name: str | None = None):
    """Decorator for API calls with circuit breaker and status-aware retry logic."""
    config = EnhancedRetryConfig(
        max_attempts=max_attempts,
        base_wait=1.0,
        max_wait=60.0,
        multiplier=2.0,
        jitter=True,
        circuit_breaker=service_name,
        timeout=30.0,
    )

    return with_enhanced_retry(
        config, operation_name=f"api_call_{service_name or 'generic'}"
    )


def with_circuit_breaker(service_name: str, config: CircuitBreakerConfig | None = None):
    """Decorator to add circuit breaker protection to a function."""
    if config is None:
        config = CircuitBreakerConfig()

    circuit_breaker = get_circuit_breaker(service_name, config)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not circuit_breaker.can_execute():
                raise CircuitBreakerError(
                    f"Circuit breaker {service_name} is open",
                    service=service_name,
                    failure_count=circuit_breaker.failure_count,
                    next_attempt_time=circuit_breaker.next_attempt_time,
                )

            try:
                result = await func(*args, **kwargs)
                circuit_breaker.record_success()
                return result
            except Exception as e:
                circuit_breaker.record_failure(e)
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not circuit_breaker.can_execute():
                raise CircuitBreakerError(
                    f"Circuit breaker {service_name} is open",
                    service=service_name,
                    failure_count=circuit_breaker.failure_count,
                    next_attempt_time=circuit_breaker.next_attempt_time,
                )

            try:
                result = func(*args, **kwargs)
                circuit_breaker.record_success()
                return result
            except Exception as e:
                circuit_breaker.record_failure(e)
                raise

        # Return appropriate wrapper based on function type

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


async def retry_async_operation(
    operation: Callable,
    max_attempts: int = 3,
    wait_min: float = 1.0,
    wait_max: float = 10.0,
    operation_name: str = "operation",
) -> Any:
    """Legacy async operation retry for backward compatibility."""
    config = EnhancedRetryConfig(
        max_attempts=max_attempts,
        base_wait=wait_min,
        max_wait=wait_max,
    )

    decorated_func = with_enhanced_retry(config, operation_name=operation_name)(
        operation
    )
    return await decorated_func()


def retry_sync_operation(
    operation: Callable,
    max_attempts: int = 3,
    wait_min: float = 1.0,
    wait_max: float = 10.0,
    operation_name: str = "operation",
) -> Any:
    """Legacy sync operation retry for backward compatibility."""
    config = EnhancedRetryConfig(
        max_attempts=max_attempts,
        base_wait=wait_min,
        max_wait=wait_max,
    )

    decorated_func = with_enhanced_retry(config, operation_name=operation_name)(
        operation
    )
    return decorated_func()


# Legacy exception classes for backward compatibility
class RetryableError(Exception):
    """Exception that indicates an operation should be retried."""

    pass


class NonRetryableError(Exception):
    """Exception that indicates an operation should not be retried."""

    pass


def create_retry_decorator(
    max_attempts: int = 3,
    wait_multiplier: float = 1.0,
    wait_min: float = 1.0,
    wait_max: float = 10.0,
    retry_on: tuple = (RetryableError,),
    stop_on: tuple = (NonRetryableError,),
):
    """Legacy create_retry_decorator for backward compatibility."""
    config = EnhancedRetryConfig(
        max_attempts=max_attempts,
        base_wait=wait_min,
        max_wait=wait_max,
        multiplier=wait_multiplier,
        retry_on=set(retry_on),
        stop_on=set(stop_on),
    )

    return with_enhanced_retry(config)


def get_circuit_breaker_status(service_name: str) -> dict[str, Any]:
    """Get the current status of a circuit breaker."""
    if service_name not in _circuit_breakers:
        return {"exists": False}

    cb = _circuit_breakers[service_name]
    return {
        "exists": True,
        "name": cb.name,
        "state": cb.state.value,
        "failure_count": cb.failure_count,
        "success_count": cb.success_count,
        "last_failure_time": cb.last_failure_time,
        "next_attempt_time": cb.next_attempt_time,
        "can_execute": cb.can_execute(),
    }


def reset_circuit_breaker(service_name: str) -> bool:
    """Manually reset a circuit breaker to closed state."""
    if service_name not in _circuit_breakers:
        return False

    cb = _circuit_breakers[service_name]
    cb.state = CircuitBreakerState.CLOSED
    cb.failure_count = 0
    cb.success_count = 0
    cb.last_failure_time = 0.0
    cb.next_attempt_time = 0.0

    logger.info(
        f"Circuit breaker {service_name} manually reset to CLOSED",
        circuit_breaker=service_name,
        state=cb.state.value,
    )

    return True


def get_all_circuit_breaker_status() -> dict[str, dict[str, Any]]:
    """Get status of all circuit breakers."""
    return {name: get_circuit_breaker_status(name) for name in _circuit_breakers.keys()}
