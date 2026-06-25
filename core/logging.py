"""Structured logging (MASTER_PLAN Task 1.2, Section 15.1).

The single home for logging configuration. ``structlog`` emits JSON in production
and a human-friendly console format in development. Every record carries the
standard fields from Section 15.1; a ``SensitiveScrubber`` processor redacts any
field whose key looks secret (Section 14.3). Correlation IDs are propagated via
context variables so they attach to every log line within a request without being
threaded through call signatures (Section 15.2).
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from typing import Any, cast

import structlog

from core.constants import REDACTED, SECRET_KEY_SUBSTRINGS

_CORRELATION_KEY = "correlation_id"

EventDict = MutableMapping[str, Any]


class SensitiveScrubber:
    """structlog processor that redacts secret-looking keys (Section 14.3).

    Any key whose lower-cased name contains a configured secret substring has its
    value replaced with ``REDACTED``. Nested mappings are scrubbed recursively.
    """

    def __init__(self, substrings: tuple[str, ...] = SECRET_KEY_SUBSTRINGS) -> None:
        self._substrings = substrings

    def __call__(self, _logger: Any, _method_name: str, event_dict: EventDict) -> EventDict:
        self._scrub(event_dict)
        return event_dict

    def _scrub(self, mapping: MutableMapping[str, Any]) -> None:
        for key, value in mapping.items():
            if isinstance(key, str) and self._is_secret(key):
                mapping[key] = REDACTED
            elif isinstance(value, MutableMapping):
                self._scrub(value)

    def _is_secret(self, key: str) -> bool:
        lowered = key.lower()
        return any(token in lowered for token in self._substrings)


def configure_logging(
    log_level: str = "INFO",
    log_format: str = "json",
    *,
    extra_processors: list[structlog.typing.Processor] | None = None,
) -> None:
    """Configure structlog + stdlib logging. Idempotent; safe to call again.

    ``extra_processors`` run after the secret scrubber and before the renderer — the
    composition root passes the Telegram alert processor (Task 10.3) here once the
    bot exists, calling this a second time to install it (the config is idempotent).
    """
    level_no = logging.getLevelNamesMapping().get(log_level.upper(), logging.INFO)

    # force=True rebinds the root handler to the current sys.stdout, so repeated
    # configuration (e.g. across tests) does not keep writing to a stale stream.
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level_no, force=True)

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        SensitiveScrubber(),
        *(extra_processors or []),
    ]

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level_no),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound logger. Pass the module/component name for the ``logger`` field."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))


def bind_correlation_id(correlation_id: str) -> None:
    """Bind a correlation ID for the current context (Section 15.2)."""
    structlog.contextvars.bind_contextvars(**{_CORRELATION_KEY: correlation_id})


def clear_correlation_id() -> None:
    """Remove the correlation ID from the current context."""
    structlog.contextvars.unbind_contextvars(_CORRELATION_KEY)


def get_correlation_id() -> str | None:
    """Return the correlation ID bound to the current context, if any (Section 15.2)."""
    value = structlog.contextvars.get_contextvars().get(_CORRELATION_KEY)
    return value if isinstance(value, str) else None


@contextmanager
def correlation_context(correlation_id: str) -> Iterator[None]:
    """Bind ``correlation_id`` for the duration of the ``with`` block."""
    bind_correlation_id(correlation_id)
    try:
        yield
    finally:
        clear_correlation_id()
