"""Timestamp parsing helpers (MASTER_PLAN Task 9.5.10).

A single place to turn an operator-supplied ISO-8601 string (a ``--at`` flag or a
``scheduled_at=`` field) into a timezone-aware UTC ``datetime``. Naive inputs are
assumed to be UTC; a trailing ``Z`` is accepted. Raises ``ValueError`` on malformed
input so callers can translate it into their own user-facing error.
"""

from __future__ import annotations

import datetime


def parse_iso_datetime(value: str) -> datetime.datetime:
    """Parse an ISO-8601 timestamp to a tz-aware UTC ``datetime`` (raises ``ValueError``)."""
    text = value.strip()
    if not text:
        raise ValueError("empty timestamp")
    if text[-1] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.datetime.fromisoformat(text)  # ValueError on malformed input
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.UTC)
    return parsed.astimezone(datetime.UTC)
