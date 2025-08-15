"""
Logging configuration for SeaDexArr.

Enhanced structured logging with production optimizations, correlation IDs,
contextual logging, performance metrics, and observability features.
"""

import asyncio
import contextvars
import logging
import logging.handlers
import time
import uuid
from typing import Any

import structlog
from rich.logging import RichHandler

# Context variables for correlation and request tracking
correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)
operation_context: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "operation_context", default_factory=dict
)
request_start_time: contextvars.ContextVar[float] = contextvars.ContextVar(
    "request_start_time", default=0.0
)


class CorrelationIDProcessor:
    """Processor to add correlation ID to log records."""

    def __call__(
        self, logger: Any, method_name: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        correlation_id_value = correlation_id.get("")
        if correlation_id_value:
            event_dict["correlation_id"] = correlation_id_value
        return event_dict


class OperationContextProcessor:
    """Processor to add operation context to log records."""

    def __call__(
        self, logger: Any, method_name: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        context = operation_context.get({})
        if context:
            event_dict.update(context)
        return event_dict


class PerformanceProcessor:
    """Processor to add performance metrics to log records."""

    def __call__(
        self, logger: Any, method_name: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        start_time = request_start_time.get(0.0)
        if start_time > 0:
            duration_ms = (time.time() - start_time) * 1000
            event_dict["duration_ms"] = round(duration_ms, 2)
        return event_dict


class AsyncContextProcessor:
    """Processor to add async task context to log records."""

    def __call__(
        self, logger: Any, method_name: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            task = asyncio.current_task()
            if task:
                event_dict["task_name"] = task.get_name()
        except RuntimeError:
            # No event loop running
            pass
        return event_dict


class SamplingFilter(logging.Filter):
    """Filter to sample log records based on level and rate."""

    def __init__(self, sample_rate: float = 1.0, high_volume_rate: float = 0.1):
        super().__init__()
        self.sample_rate = sample_rate
        self.high_volume_rate = high_volume_rate
        self.counter = 0

    def filter(self, record: logging.LogRecord) -> bool:
        self.counter += 1

        # Always log errors and warnings
        if record.levelno >= logging.WARNING:
            return True

        # Sample INFO and DEBUG based on rate
        if record.levelno >= logging.INFO:
            return (self.counter % int(1 / self.sample_rate)) == 0

        # Higher sampling for DEBUG (high volume)
        return (self.counter % int(1 / self.high_volume_rate)) == 0


class EnhancedStructuredLogger:
    """Enhanced wrapper for structured logging with convenience methods and context management."""

    def __init__(self, logger_name: str):
        self.logger = structlog.get_logger(logger_name)
        self._logger_name = logger_name

    def with_correlation_id(
        self, correlation_id_value: str | None = None
    ) -> "EnhancedStructuredLogger":
        """Create logger instance with correlation ID context."""
        if correlation_id_value is None:
            correlation_id_value = str(uuid.uuid4())

        correlation_id.set(correlation_id_value)
        return self

    def with_operation(
        self, operation_name: str, **context: Any
    ) -> "EnhancedStructuredLogger":
        """Create logger instance with operation context."""
        ctx = {"operation": operation_name, **context}
        operation_context.set(ctx)
        request_start_time.set(time.time())
        return self

    def with_user_context(
        self, username: str, **context: Any
    ) -> "EnhancedStructuredLogger":
        """Create logger instance with user context."""
        ctx = operation_context.get({}).copy()
        ctx.update({"username": username, **context})
        operation_context.set(ctx)
        return self

    def with_service_context(
        self, service: str, **context: Any
    ) -> "EnhancedStructuredLogger":
        """Create logger instance with service context."""
        ctx = operation_context.get({}).copy()
        ctx.update({"service": service, **context})
        operation_context.set(ctx)
        return self

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an info message with structured data."""
        self.logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a warning message with structured data."""
        self.logger.warning(message, **kwargs)

    def error(
        self, message: str, error: Exception | None = None, **kwargs: Any
    ) -> None:
        """Log an error message with structured data and exception details."""
        if error:
            kwargs.update(
                {
                    "error": str(error),
                    "error_type": type(error).__name__,
                    "error_module": type(error).__module__,
                }
            )
            if hasattr(error, "__traceback__") and error.__traceback__:
                import traceback

                kwargs["traceback"] = traceback.format_exception(
                    type(error), error, error.__traceback__
                )
        self.logger.error(message, **kwargs)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a debug message with structured data."""
        self.logger.debug(message, **kwargs)

    def critical(
        self, message: str, error: Exception | None = None, **kwargs: Any
    ) -> None:
        """Log a critical message with structured data."""
        if error:
            kwargs.update(
                {
                    "error": str(error),
                    "error_type": type(error).__name__,
                    "error_module": type(error).__module__,
                }
            )
        self.logger.critical(message, **kwargs)

    def performance(self, message: str, duration_ms: float, **kwargs: Any) -> None:
        """Log performance metrics."""
        kwargs["duration_ms"] = round(duration_ms, 2)
        kwargs["performance_metric"] = True
        self.logger.info(message, **kwargs)

    def audit(self, action: str, **kwargs: Any) -> None:
        """Log audit events."""
        kwargs.update(
            {
                "audit": True,
                "action": action,
                "timestamp": time.time(),
            }
        )
        self.logger.info(f"AUDIT: {action}", **kwargs)

    def security(self, event: str, level: str = "info", **kwargs: Any) -> None:
        """Log security events."""
        kwargs.update(
            {
                "security_event": True,
                "security_level": level,
            }
        )
        getattr(self.logger, level)(f"SECURITY: {event}", **kwargs)


def setup_enhanced_logging(
    verbose: bool = False,
    quiet: bool = False,
    json_logs: bool = False,
    log_file: str | None = None,
    log_rotation: bool = True,
    max_file_size: int = 100 * 1024 * 1024,  # 100MB
    backup_count: int = 5,
    sample_rate: float = 1.0,
    enable_performance_logging: bool = True,
    enable_security_logging: bool = True,
) -> None:
    """Configure enhanced structured logging for the application."""

    # Set log level
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    # Enhanced processors for all configurations
    base_processors = [
        CorrelationIDProcessor(),
        OperationContextProcessor(),
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
    ]

    # Add optional processors
    if enable_performance_logging:
        base_processors.append(PerformanceProcessor())

    base_processors.append(AsyncContextProcessor())

    if json_logs:
        # Production JSON output processors
        json_processors = [
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ]
        processors = [*base_processors, *json_processors]

        # Configure standard library logging for JSON with rotation
        if log_file and log_rotation:
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=max_file_size,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(level)

            # Add sampling filter for high-volume logs
            sampling_filter = SamplingFilter(sample_rate=sample_rate)
            file_handler.addFilter(sampling_filter)

            logging.basicConfig(
                format="%(message)s",
                level=level,
                handlers=[file_handler],
            )
        elif log_file:
            logging.basicConfig(
                format="%(message)s", level=level, filename=log_file, encoding="utf-8"
            )
        else:
            logging.basicConfig(
                format="%(message)s",
                stream=None,
                level=level,
            )
    else:
        # Development console output
        console_processors = [
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S.%f"),
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.LINENO,
                ]
            ),
            structlog.dev.ConsoleRenderer(colors=True),
        ]
        processors = [*base_processors, *console_processors]

        # Configure Rich handler for beautiful console output
        rich_handler = RichHandler(
            show_time=False,  # We handle time in structlog
            show_path=False,
            markup=True,
            rich_tracebacks=True,
            tracebacks_show_locals=verbose,
        )

        # Add sampling filter for development
        if sample_rate < 1.0:
            sampling_filter = SamplingFilter(sample_rate=sample_rate)
            rich_handler.addFilter(sampling_filter)

        handlers = [rich_handler]

        # Add file handler in development if specified
        if log_file:
            if log_rotation:
                file_handler = logging.handlers.RotatingFileHandler(
                    log_file,
                    maxBytes=max_file_size,
                    backupCount=backup_count,
                    encoding="utf-8",
                )
            else:
                file_handler = logging.FileHandler(log_file, encoding="utf-8")

            file_handler.setLevel(level)
            file_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            file_handler.setFormatter(file_formatter)
            handlers.append(file_handler)

        logging.basicConfig(level=level, format="%(message)s", handlers=handlers)

    # Configure structlog with enhanced settings
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure specific loggers for better control
    configure_third_party_loggers(level, verbose)


def configure_third_party_loggers(level: int, verbose: bool) -> None:
    """Configure third-party library loggers."""
    # Reduce noise from HTTP libraries
    logging.getLogger("httpx").setLevel(
        logging.WARNING if not verbose else logging.INFO
    )
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Rich logging adjustments
    logging.getLogger("rich").setLevel(logging.WARNING)

    # Asyncio debug logging
    if verbose:
        logging.getLogger("asyncio").setLevel(logging.DEBUG)
    else:
        logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str) -> EnhancedStructuredLogger:
    """Get an enhanced structured logger instance."""
    return EnhancedStructuredLogger(name)


def get_correlation_id() -> str:
    """Get the current correlation ID."""
    return correlation_id.get("")


def set_correlation_id(correlation_id_value: str) -> None:
    """Set the correlation ID for the current context."""
    correlation_id.set(correlation_id_value)


def generate_correlation_id() -> str:
    """Generate a new correlation ID."""
    return str(uuid.uuid4())


def clear_context() -> None:
    """Clear all logging context variables."""
    correlation_id.set("")
    operation_context.set({})
    request_start_time.set(0.0)


class LoggingContextManager:
    """Context manager for structured logging contexts."""

    def __init__(
        self,
        logger: EnhancedStructuredLogger,
        operation: str,
        correlation_id_value: str | None = None,
        **context: Any,
    ):
        self.logger = logger
        self.operation = operation
        self.correlation_id_value = correlation_id_value or generate_correlation_id()
        self.context = context
        self._old_correlation_id = None
        self._old_context = None
        self._old_start_time = None

    def __enter__(self) -> EnhancedStructuredLogger:
        # Store old values
        self._old_correlation_id = correlation_id.get("")
        self._old_context = operation_context.get({})
        self._old_start_time = request_start_time.get(0.0)

        # Set new values
        correlation_id.set(self.correlation_id_value)
        operation_context.set({"operation": self.operation, **self.context})
        request_start_time.set(time.time())

        self.logger.info(f"Starting operation: {self.operation}", **self.context)
        return self.logger

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - request_start_time.get(time.time())) * 1000

        if exc_type:
            self.logger.error(
                f"Operation failed: {self.operation}",
                error=str(exc_val),
                error_type=exc_type.__name__,
                duration_ms=round(duration_ms, 2),
                **self.context,
            )
        else:
            self.logger.info(
                f"Operation completed: {self.operation}",
                duration_ms=round(duration_ms, 2),
                **self.context,
            )

        # Restore old values
        correlation_id.set(self._old_correlation_id or "")
        operation_context.set(self._old_context or {})
        request_start_time.set(self._old_start_time or 0.0)


def operation_logger(
    operation_name: str, correlation_id_value: str | None = None, **context: Any
) -> LoggingContextManager:
    """Create a logging context manager for operations."""
    logger = get_logger(__name__)
    return LoggingContextManager(
        logger, operation_name, correlation_id_value, **context
    )


# Legacy compatibility
def setup_logging(*args, **kwargs) -> None:
    """Legacy setup_logging function for backward compatibility."""
    setup_enhanced_logging(*args, **kwargs)
