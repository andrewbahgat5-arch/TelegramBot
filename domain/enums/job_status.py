"""Job lifecycle states (MASTER_PLAN 12.3, LOCKED state machine)."""

from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    """The state of a download job.

    Persisted as the ``jobs.status`` VARCHAR(30) column. String values are the
    on-disk representation and must never change (MASTER_PLAN 9.4: removing or
    renaming a value would break stored records).
    """

    CREATED = "created"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"  # transient failure; eligible for retry
    RETRY_QUEUED = "retry_queued"
    PERMANENTLY_FAILED = "permanently_failed"
    TIMED_OUT = "timed_out"  # transient until a worker re-evaluates
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """Whether this is a terminal state (MASTER_PLAN 12.3)."""
        return self in _TERMINAL_STATES


# Terminal states per MASTER_PLAN 12.3. ``TIMED_OUT`` is explicitly NOT terminal.
_TERMINAL_STATES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.COMPLETED,
        JobStatus.PERMANENTLY_FAILED,
        JobStatus.CANCELLED,
    }
)
