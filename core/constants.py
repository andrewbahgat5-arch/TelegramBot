"""Cross-cutting primitive constants (MASTER_PLAN Task 1.5).

Only framework-free primitives live here. The strongly-typed enumerations
(``JobStatus``, ``UserRole``, ``MediaFormat``, ``Quality``, ``ErrorType``,
``AdType``) live in ``domain/enums/`` per the file-placement rules (Section 7.1)
and the Component Catalog (Section 9.4). ``core`` may not import ``domain``,
so anything shared between the two (e.g. the secret-redaction key list used by
both ``core/logging.py`` and ``core/sentry.py``) is defined here as primitives.
"""

from __future__ import annotations

from typing import Final

# --- Queue priority bands (MASTER_PLAN 12.2) ------------------------------
# Lower score sorts first. FIFO within a band.
PRIORITY_URGENT: Final[int] = 0
PRIORITY_HIGH: Final[int] = 500
PRIORITY_NORMAL: Final[int] = 1000
PRIORITY_LOW: Final[int] = 2000

# Default worker kind (MASTER_PLAN D-021).
WORKER_KIND_DOWNLOAD: Final[str] = "download"


def priority_score(base: int, unix_time_ms: int) -> float:
    """Queue score for a job (MASTER_PLAN 12.2).

    ``score = base + (unix_time_ms / 1000)``. Lower sorts first, preserving
    FIFO ordering within a priority band.
    """
    return base + (unix_time_ms / 1000)


# --- Secret redaction (MASTER_PLAN 14.3 / 15.1) ---------------------------
# Placeholder written in place of any redacted value.
REDACTED: Final[str] = "***REDACTED***"

# A log/Sentry/​repr key is redacted if its lower-cased name contains any of
# these substrings.
SECRET_KEY_SUBSTRINGS: Final[tuple[str, ...]] = (
    "secret",
    "token",
    "password",
    "passwd",
    "dsn",
    "api_key",
    "apikey",
    "authorization",
)

# Environment variables that hold secrets (MASTER_PLAN 13.2 / 14.3). Used by
# ``Settings.__repr__`` to redact, and as a belt-and-braces list for scrubbers.
SECRET_ENV_KEYS: Final[tuple[str, ...]] = (
    "BOT_TOKEN",
    "BOT_WEBHOOK_SECRET",
    "DB_PASSWORD",
    "SENTRY_DSN",
)

# --- Structured logging (MASTER_PLAN 15.1) --------------------------------
# Standard fields present (when applicable) on every log record. The "?"-marked
# fields in the plan are optional and only bound when in scope.
LOG_STANDARD_FIELDS: Final[tuple[str, ...]] = (
    "timestamp",
    "level",
    "logger",
    "event",
    "correlation_id",
    "user_id",
    "job_id",
    "worker_id",
    "duration_ms",
    "component",
)

# --- Layered timeouts (MASTER_PLAN D-025), seconds ------------------------
HANDLER_TIMEOUT_SECONDS: Final[float] = 5.0
SERVICE_TIMEOUT_SECONDS: Final[float] = 15.0
DEFAULT_WORKER_TIMEOUT_SECONDS: Final[float] = 300.0

# --- Misc tunables fixed in code (not operator-configurable) --------------
# Debounce window for ``users.last_activity_at`` writes (MASTER_PLAN 9.2; the
# Sprint 4 validation checklist fixes this at "at most every 5 s per user").
LAST_ACTIVITY_DEBOUNCE_SECONDS: Final[int] = 5
