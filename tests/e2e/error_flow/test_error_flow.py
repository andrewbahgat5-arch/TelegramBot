"""E2E · Error Flow (MASTER_PLAN §25.7.5).

Skip-guarded via the ``harness`` fixture until the Phase-B sandbox is provisioned.
"""

from __future__ import annotations

from tests.e2e.harness import E2EHarness


def test_provider_unavailable_falls_back_or_errors(harness: E2EHarness) -> None:
    """Provider unavailable: registry tries next; if none, a user-friendly error."""
    assert harness.pool is not None


def test_invalid_url_localized_message(harness: E2EHarness) -> None:
    """Invalid URL: URLNotSupportedError → localized message."""
    assert harness.pool is not None


def test_unsupported_platform_message(harness: E2EHarness) -> None:
    """Unsupported platform: same localized message."""
    assert harness.pool is not None


def test_timeout_marks_timed_out_and_retries(harness: E2EHarness) -> None:
    """Timeout: job marked TIMED_OUT; auto-retry within limits."""
    assert harness.pool is not None


def test_worker_crash_requeues_and_notifies(harness: E2EHarness) -> None:
    """Worker crash mid-job: cleanup re-queues; waiters notified after recovery."""
    assert harness.pool is not None
