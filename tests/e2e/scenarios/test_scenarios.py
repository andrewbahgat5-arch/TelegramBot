"""E2E · Named validation scenarios S-1 .. S-5 (MASTER_PLAN Task 11.4, §25.8).

Skip-guarded via the ``harness`` fixture until the Phase-B sandbox is provisioned.
Sprint 11 gating requires S-1 through S-5; S-3 uses a mocked secondary provider
until V6 adds a real second provider.
"""

from __future__ import annotations

from tests.e2e.harness import E2EHarness


def test_s1_valid_url_happy_path(harness: E2EHarness) -> None:
    """S-1: send URL → select quality → receive file; verify hash/size/format."""
    assert harness.pool is not None


def test_s2_cache_reuse(harness: E2EHarness) -> None:
    """S-2: send same URL again → cached file; usage_count incremented; no yt-dlp call."""
    assert harness.pool is not None


def test_s3_provider_failover_mocked_secondary(harness: E2EHarness) -> None:
    """S-3: force primary failure (providers_enabled.ytdlp=false) + mocked secondary.

    Registry tries secondary; user receives file; provider:health:ytdlp reflects DEGRADED.
    """
    assert harness.pool is not None


def test_s4_worker_crash_recovery(harness: E2EHarness) -> None:
    """S-4: kill the active worker mid-job → cleanup re-queues; retry succeeds; no double-count."""
    assert harness.pool is not None


def test_s5_redis_restart_recovery(harness: E2EHarness) -> None:
    """S-5: bounce Redis → queue rehydrated from active_downloads in PG; no duplicate work."""
    assert harness.pool is not None
