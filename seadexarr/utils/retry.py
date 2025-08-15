"""
Retry logic utilities for SeaDexArr.

Functional retry decorators and utilities using tenacity.
"""

import functools
from collections.abc import Callable
from typing import Any

import structlog
from tenacity import (
    AsyncRetrying,
    RetryError,
    Retrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)


def with_retry(
    max_attempts: int = 3,
    wait_min: float = 1.0,
    wait_max: float = 10.0,
    retry_exceptions: tuple = (Exception,),
    stop_on_exceptions: tuple | None = None,
):
    """
    Decorator to add retry logic to functions with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        wait_min: Minimum wait time in seconds
        wait_max: Maximum wait time in seconds
        retry_exceptions: Exception types to retry on
        stop_on_exceptions: Exception types that should not be retried
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            retry_config = AsyncRetrying(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
                retry=retry_if_exception_type(retry_exceptions),
                before_sleep=before_sleep_log(logger, structlog.stdlib.WARNING),
                reraise=True,
            )

            # Don't retry on certain exceptions
            if stop_on_exceptions:

                def should_retry(retry_state):
                    if retry_state.outcome.failed:
                        exception = retry_state.outcome.exception()
                        if isinstance(exception, stop_on_exceptions):
                            return False
                    return retry_if_exception_type(retry_exceptions)(retry_state)

                retry_config.retry = should_retry

            try:
                return await retry_config(func, *args, **kwargs)
            except RetryError as e:
                # Log final failure and re-raise the original exception
                logger.error(
                    "Function failed after all retries",
                    function=func.__name__,
                    attempts=max_attempts,
                    original_error=str(e.last_attempt.exception()),
                )
                raise e.last_attempt.exception()

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            retry_config = Retrying(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
                retry=retry_if_exception_type(retry_exceptions),
                before_sleep=before_sleep_log(logger, structlog.stdlib.WARNING),
                reraise=True,
            )

            # Don't retry on certain exceptions
            if stop_on_exceptions:

                def should_retry(retry_state):
                    if retry_state.outcome.failed:
                        exception = retry_state.outcome.exception()
                        if isinstance(exception, stop_on_exceptions):
                            return False
                    return retry_if_exception_type(retry_exceptions)(retry_state)

                retry_config.retry = should_retry

            try:
                return retry_config(func, *args, **kwargs)
            except RetryError as e:
                # Log final failure and re-raise the original exception
                logger.error(
                    "Function failed after all retries",
                    function=func.__name__,
                    attempts=max_attempts,
                    original_error=str(e.last_attempt.exception()),
                )
                raise e.last_attempt.exception()

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def with_http_retry(max_attempts: int = 3):
    """Decorator specifically for HTTP requests with appropriate retry logic."""
    import httpx

    return with_retry(
        max_attempts=max_attempts,
        wait_min=1.0,
        wait_max=30.0,
        retry_exceptions=(
            httpx.TimeoutException,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
        ),
        stop_on_exceptions=(httpx.HTTPStatusError,),  # Don't retry on 4xx/5xx errors
    )


def with_api_retry(max_attempts: int = 3):
    """Decorator for API calls with more aggressive retry on certain status codes."""
    import httpx

    def should_retry_on_status(exception):
        """Determine if we should retry based on HTTP status code."""
        if isinstance(exception, httpx.HTTPStatusError):
            # Retry on 5xx server errors and rate limiting
            return (
                exception.response.status_code >= 500
                or exception.response.status_code == 429
            )
        return True

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            retry_config = AsyncRetrying(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential(multiplier=2, min=1.0, max=60.0),
                before_sleep=before_sleep_log(logger, structlog.stdlib.WARNING),
                reraise=True,
            )

            def custom_retry(retry_state):
                if retry_state.outcome.failed:
                    exception = retry_state.outcome.exception()
                    return should_retry_on_status(exception)
                return False

            retry_config.retry = custom_retry

            try:
                return await retry_config(func, *args, **kwargs)
            except RetryError as e:
                logger.error(
                    "API call failed after all retries",
                    function=func.__name__,
                    attempts=max_attempts,
                    original_error=str(e.last_attempt.exception()),
                )
                raise e.last_attempt.exception()

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            retry_config = Retrying(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential(multiplier=2, min=1.0, max=60.0),
                before_sleep=before_sleep_log(logger, structlog.stdlib.WARNING),
                reraise=True,
            )

            def custom_retry(retry_state):
                if retry_state.outcome.failed:
                    exception = retry_state.outcome.exception()
                    return should_retry_on_status(exception)
                return False

            retry_config.retry = custom_retry

            try:
                return retry_config(func, *args, **kwargs)
            except RetryError as e:
                logger.error(
                    "API call failed after all retries",
                    function=func.__name__,
                    attempts=max_attempts,
                    original_error=str(e.last_attempt.exception()),
                )
                raise e.last_attempt.exception()

        # Return appropriate wrapper based on function type
        import asyncio

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
    """
    Retry an async operation with exponential backoff.

    Args:
        operation: Async function to retry
        max_attempts: Maximum number of attempts
        wait_min: Minimum wait time in seconds
        wait_max: Maximum wait time in seconds
        operation_name: Name for logging purposes

    Returns:
        Result of the operation

    Raises:
        The last exception if all retries fail
    """
    retry_config = AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
        before_sleep=before_sleep_log(logger, structlog.stdlib.WARNING),
        reraise=True,
    )

    try:
        return await retry_config(operation)
    except RetryError as e:
        logger.error(
            "Operation failed after all retries",
            operation=operation_name,
            attempts=max_attempts,
            original_error=str(e.last_attempt.exception()),
        )
        raise e.last_attempt.exception()


def retry_sync_operation(
    operation: Callable,
    max_attempts: int = 3,
    wait_min: float = 1.0,
    wait_max: float = 10.0,
    operation_name: str = "operation",
) -> Any:
    """
    Retry a sync operation with exponential backoff.

    Args:
        operation: Function to retry
        max_attempts: Maximum number of attempts
        wait_min: Minimum wait time in seconds
        wait_max: Maximum wait time in seconds
        operation_name: Name for logging purposes

    Returns:
        Result of the operation

    Raises:
        The last exception if all retries fail
    """
    retry_config = Retrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
        before_sleep=before_sleep_log(logger, structlog.stdlib.WARNING),
        reraise=True,
    )

    try:
        return retry_config(operation)
    except RetryError as e:
        logger.error(
            "Operation failed after all retries",
            operation=operation_name,
            attempts=max_attempts,
            original_error=str(e.last_attempt.exception()),
        )
        raise e.last_attempt.exception()


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
    """
    Create a custom retry decorator with specific configuration.

    Args:
        max_attempts: Maximum number of attempts
        wait_multiplier: Multiplier for exponential backoff
        wait_min: Minimum wait time in seconds
        wait_max: Maximum wait time in seconds
        retry_on: Exception types to retry on
        stop_on: Exception types to never retry

    Returns:
        Configured retry decorator
    """
    return with_retry(
        max_attempts=max_attempts,
        wait_min=wait_min,
        wait_max=wait_max,
        retry_exceptions=retry_on,
        stop_on_exceptions=stop_on,
    )
