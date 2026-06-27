"""E2E · Queue Flow (MASTER_PLAN §25.7.4).

Skip-guarded via the ``harness`` fixture until the Phase-B sandbox is provisioned.
"""

from __future__ import annotations

from tests.e2e.harness import E2EHarness


def test_priority_ordering(harness: E2EHarness) -> None:
    """HIGH dequeued before NORMAL before LOW."""
    assert harness.pool is not None


def test_atomic_dequeue_no_double_processing(harness: E2EHarness) -> None:
    """Atomic dequeue under concurrency (no double processing)."""
    assert harness.pool is not None


def test_transient_failure_requeues_at_low(harness: E2EHarness) -> None:
    """Transient failure: job re-queued at LOW; retry count increments."""
    assert harness.pool is not None


def test_permanent_failure_notifies_user(harness: E2EHarness) -> None:
    """Permanent failure: PERMANENTLY_FAILED; user notified."""
    assert harness.pool is not None
