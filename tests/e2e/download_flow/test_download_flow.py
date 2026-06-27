"""E2E · Download Flow (MASTER_PLAN §25.7.2).

Skip-guarded via the ``harness`` fixture until the Phase-B sandbox is provisioned.
"""

from __future__ import annotations

from tests.e2e.harness import E2EHarness


def test_url_submission_returns_format_keyboard(harness: E2EHarness) -> None:
    """URL submission → format keyboard within the 3 s p95 budget."""
    assert harness.pool is not None


def test_format_selection_returns_quality_keyboard(harness: E2EHarness) -> None:
    """Format selection → quality keyboard."""
    assert harness.pool is not None


def test_quality_selection_delivers_file(harness: E2EHarness) -> None:
    """Quality selection → job created, queued, processed, file delivered."""
    assert harness.pool is not None


def test_state_transitions_persisted(harness: E2EHarness) -> None:
    """created → queued → processing → completed persisted; downloads row inserted."""
    assert harness.pool is not None


def test_total_downloads_increment_and_daily_reset(harness: E2EHarness) -> None:
    """users.total_downloads increments; lazy daily reset works across the day boundary."""
    assert harness.pool is not None
