"""
Logging configuration for SeaDexArr.
"""

import logging
from typing import Any

import structlog
from rich.logging import RichHandler


class StructuredLogger:
    """Wrapper for structured logging with convenience methods."""

    def __init__(self, logger_name: str):
        self.logger = structlog.get_logger(logger_name)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an info message with structured data."""
        self.logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a warning message with structured data."""
        self.logger.warning(message, **kwargs)

    def error(
        self, message: str, error: Exception | None = None, **kwargs: Any
    ) -> None:
        """Log an error message with structured data."""
        if error:
            kwargs["error"] = str(error)
            kwargs["error_type"] = type(error).__name__
        self.logger.error(message, **kwargs)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a debug message with structured data."""
        self.logger.debug(message, **kwargs)


def setup_logging(
    verbose: bool = False,
    quiet: bool = False,
    json_logs: bool = False,
    log_file: str | None = None,
) -> None:
    """Configure structured logging for the application."""

    # Set log level
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    # Base processors for all configurations
    base_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
    ]

    if json_logs:
        # JSON output processors
        json_processors: list[Any] = [
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
        processors = [*base_processors, *json_processors]

        # Configure standard library logging for JSON
        logging.basicConfig(
            format="%(message)s",
            stream=None,
            level=level,
        )
    else:
        # Human-readable console output
        console_processors: list[Any] = [
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
            structlog.dev.ConsoleRenderer(colors=True),
        ]
        processors = [*base_processors, *console_processors]

        # Configure Rich handler for beautiful console output
        rich_handler = RichHandler(
            show_time=False,  # We handle time in structlog
            show_path=False,
            markup=True,
            rich_tracebacks=True,
        )

        logging.basicConfig(level=level, format="%(message)s", handlers=[rich_handler])

    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        logging.getLogger().addHandler(file_handler)

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name)
