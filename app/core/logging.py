"""Structured logging setup using structlog with correlation IDs."""

import logging
from contextvars import ContextVar

import structlog
from structlog.types import EventDict, WrappedLogger

# Correlation ID for async request tracing
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def add_correlation_id(
    _logger: WrappedLogger, _method_name: str, event_dict: EventDict
) -> EventDict:
    """Add correlation ID to log event if set."""
    correlation_id = correlation_id_var.get()
    if correlation_id:
        event_dict["correlation_id"] = correlation_id
    return event_dict


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structured logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper()),
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_correlation_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, log_level.upper())),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)  # type: ignore[no-any-return]


def set_correlation_id(correlation_id: str) -> None:
    """Set correlation ID for current async context.

    Args:
        correlation_id: Unique ID for request tracing
    """
    correlation_id_var.set(correlation_id)


def get_correlation_id() -> str:
    """Get correlation ID from current async context.

    Returns:
        Current correlation ID or empty string if not set
    """
    return correlation_id_var.get()
