"""Unit tests for CleanupWorker DB-maintenance duties (MASTER_PLAN Task 10.5)."""

from __future__ import annotations

from pathlib import Path

from infrastructure.database.partitioning import partition_name, partitions_to_drop
from workers.cleanup_worker import CleanupWorker


def test_partitions_to_drop_selects_only_old_months_for_table() -> None:
    existing = [
        "public.downloads_y2025m12",
        "public.downloads_y2026m01",
        "public.downloads_y2026m06",
        "public.jobs_y2025m01",  # different table — ignored
        "downloads_unrelated",  # not a partition name — ignored
    ]
    dropped = partitions_to_drop(existing, table="downloads", cutoff_year=2026, cutoff_month=1)
    assert dropped == ["public.downloads_y2025m12"]  # only the month before 2026-01


def test_partitions_to_drop_handles_bare_and_qualified_names() -> None:
    existing = [partition_name("error_logs", 2025, 3), "schema.error_logs_y2025m04"]
    dropped = partitions_to_drop(existing, table="error_logs", cutoff_year=2025, cutoff_month=5)
    assert set(dropped) == {"error_logs_y2025m03", "schema.error_logs_y2025m04"}


class _FakeMaintenance:
    def __init__(self) -> None:
        self.calls: list[object] = []
        self.ensure_raises = False

    async def ensure_partitions(self) -> list[str]:
        self.calls.append("ensure")
        if self.ensure_raises:
            raise RuntimeError("partition boom")
        return ["downloads_y2026m06"]

    async def drop_expired_partitions(self, retention_days: dict[str, int]) -> list[str]:
        self.calls.append(("drop", retention_days))
        return []

    async def sweep_orphans(self) -> tuple[int, int]:
        self.calls.append("sweep")
        return (1, 2)

    async def reclaim_stalled_jobs(self, *, older_than_seconds: float | None = None) -> int:
        self.calls.append(("reclaim", older_than_seconds))
        return 0


async def _retention() -> dict[str, int]:
    return {"downloads": 365, "jobs": 90, "error_logs": 90}


async def test_maintain_once_runs_all_duties(tmp_path: Path) -> None:
    fake = _FakeMaintenance()
    worker = CleanupWorker(tmp_path, maintenance=fake, retention_reader=_retention)
    await worker.maintain_once()
    assert "ensure" in fake.calls
    assert "sweep" in fake.calls
    # Backstop reclaim runs age-gated (never reap-all on the periodic cadence).
    assert ("reclaim", worker._stalled_ceiling) in fake.calls
    assert ("drop", {"downloads": 365, "jobs": 90, "error_logs": 90}) in fake.calls


async def test_maintain_once_isolates_duty_failures(tmp_path: Path) -> None:
    fake = _FakeMaintenance()
    fake.ensure_raises = True
    worker = CleanupWorker(tmp_path, maintenance=fake, retention_reader=_retention)
    # ensure_partitions raising must not prevent the orphan sweep and retention drop.
    await worker.maintain_once()
    assert "sweep" in fake.calls
    assert any(isinstance(c, tuple) and c[0] == "drop" for c in fake.calls)


async def test_maintain_once_without_maintenance_is_noop(tmp_path: Path) -> None:
    worker = CleanupWorker(tmp_path)
    await worker.maintain_once()  # no maintenance injected → returns immediately
