"""ReportWriter (MASTER_PLAN §25.15.8, §25.14).

Formats and appends entries to the LOCKED report files. Append-only: it never
edits prior content. Tests point it at a temp file; live load runs (Phase B) point
it at the real ``PERFORMANCE_REPORT.md``.
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from pathlib import Path

from tests.simulation.metrics.collector import RunSummary


class ReportWriter:
    def __init__(self, path: Path) -> None:
        self._path = path

    def append(self, block: str) -> None:
        """Append a markdown block to the target file (append-only)."""
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write("\n" + block.rstrip() + "\n")

    def performance_entry(
        self,
        *,
        level: str,
        profiles: str,
        git_sha: str,
        summary: RunSummary,
        seed: int | None,
        transport: str,
        notes: str = "",
    ) -> str:
        """Format and append a load-level entry; return the block written."""
        ts = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M UTC")
        rows = "\n".join(f"| {k} | {v} |" for k, v in summary.as_dict().items())
        block = (
            f"### {ts} — Load {level} — profiles: {profiles}\n\n"
            f"| Field | Value |\n|---|---|\n"
            f"| Git SHA | {git_sha} |\n"
            f"| Level | {level} |\n"
            f"| Seed | {seed} |\n"
            f"| Transport | {transport} |\n"
            f"{rows}\n"
            f"| Notes | {notes} |\n"
        )
        self.append(block)
        return block

    def custom_entry(self, title: str, fields: Mapping[str, object]) -> str:
        """Append a generic titled table entry; return the block written."""
        rows = "\n".join(f"| {k} | {v} |" for k, v in fields.items())
        block = f"### {title}\n\n| Field | Value |\n|---|---|\n{rows}\n"
        self.append(block)
        return block
