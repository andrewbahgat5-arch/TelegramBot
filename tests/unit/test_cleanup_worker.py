"""Unit tests for the minimal CleanupWorker sweep (MASTER_PLAN Task 6.10)."""

from __future__ import annotations

import os
import time
from pathlib import Path

from workers.cleanup_worker import CleanupWorker


def test_sweep_removes_old_keeps_fresh(tmp_path: Path) -> None:
    old_file = tmp_path / "old.mp4"
    old_file.write_bytes(b"x")
    old_dir = tmp_path / "old_job"
    old_dir.mkdir()
    (old_dir / "a.part").write_bytes(b"y")
    fresh = tmp_path / "fresh.mp4"
    fresh.write_bytes(b"z")

    now = time.time()
    stale = now - 3600
    os.utime(old_file, (stale, stale))
    os.utime(old_dir, (stale, stale))

    removed = CleanupWorker(tmp_path, max_age_seconds=60).sweep_once(now=now)

    assert removed == 2
    assert not old_file.exists()
    assert not old_dir.exists()
    assert fresh.exists()


def test_sweep_missing_dir_is_noop(tmp_path: Path) -> None:
    worker = CleanupWorker(tmp_path / "does-not-exist")
    assert worker.sweep_once() == 0
