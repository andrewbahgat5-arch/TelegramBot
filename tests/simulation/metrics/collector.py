"""MetricsCollector (MASTER_PLAN §25.15.5).

Collects per-action outcomes and computes the application-layer metrics in the
LOCKED catalog: response-time percentiles, error rate, throughput, and the
abuse-blocked count. Queue/Redis/DB/provider layers are populated by the live
transport in Phase B; the dry-run stub reports the application layer it can
observe.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tests.simulation.actions import ActionResult


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile of an already-sorted list (empty → 0.0)."""
    if not sorted_values:
        return 0.0
    rank = max(1, min(len(sorted_values), round(pct / 100 * len(sorted_values))))
    return sorted_values[rank - 1]


@dataclass(frozen=True, slots=True)
class RunSummary:
    total: int
    succeeded: int
    failed: int
    blocked: int
    successful_downloads: int
    blocked_downloads: int
    error_rate: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    throughput_per_s: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "blocked": self.blocked,
            "successful_downloads": self.successful_downloads,
            "blocked_downloads": self.blocked_downloads,
            "error_rate": round(self.error_rate, 4),
            "p50_ms": round(self.p50_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "p99_ms": round(self.p99_ms, 2),
            "throughput_per_s": round(self.throughput_per_s, 2),
        }


@dataclass
class MetricsCollector:
    """Accumulates :class:`ActionResult`s and derives a :class:`RunSummary`."""

    results: list[ActionResult] = field(default_factory=list)

    def record(self, result: ActionResult) -> None:
        self.results.append(result)

    def summarize(self, wall_clock_s: float) -> RunSummary:
        total = len(self.results)
        latencies = sorted(r.latency_s * 1000 for r in self.results)
        succeeded = sum(1 for r in self.results if r.success)
        blocked = sum(1 for r in self.results if r.blocked)
        failed = total - succeeded
        downloads = [r for r in self.results if r.kind.value in ("click_quality", "click_resend")]
        successful_downloads = sum(1 for r in downloads if r.success)
        blocked_downloads = sum(1 for r in downloads if r.blocked)
        error_rate = (failed / total) if total else 0.0
        throughput = (total / wall_clock_s) if wall_clock_s > 0 else 0.0
        return RunSummary(
            total=total,
            succeeded=succeeded,
            failed=failed,
            blocked=blocked,
            successful_downloads=successful_downloads,
            blocked_downloads=blocked_downloads,
            error_rate=error_rate,
            p50_ms=_percentile(latencies, 50),
            p95_ms=_percentile(latencies, 95),
            p99_ms=_percentile(latencies, 99),
            throughput_per_s=throughput,
        )
