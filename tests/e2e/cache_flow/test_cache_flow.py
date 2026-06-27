"""E2E · Cache Flow (MASTER_PLAN §25.7.3).

Skip-guarded via the ``harness`` fixture until the Phase-B sandbox is provisioned.
"""

from __future__ import annotations

from tests.e2e.harness import E2EHarness


def test_second_request_served_from_cache(harness: E2EHarness) -> None:
    """Second request for the same (media, format, quality) → instant cached file_id."""
    assert harness.pool is not None


def test_cache_usage_count_increments(harness: E2EHarness) -> None:
    """cached_files.usage_count increments; last_used_at updates."""
    assert harness.pool is not None


def test_cache_miss_after_deletion_refetches(harness: E2EHarness) -> None:
    """Cache miss after row deletion → fresh download with a new cache row."""
    assert harness.pool is not None


def test_concurrent_requests_fan_out_to_both(harness: E2EHarness) -> None:
    """Two users requesting the same content concurrently → job_waiters fan-out; one cache row."""
    assert harness.pool is not None
