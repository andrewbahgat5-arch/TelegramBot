"""Prometheus metrics registry (MASTER_PLAN Task 10.2, Section 15.3, D-050).

The single home for the metric objects in Section 15.3. Call sites use the small
``record_*`` / ``observe_*`` helpers rather than touching the metric objects
directly, so label sets stay consistent and bounded.

Cross-process model (D-050): counters and histograms are incremented in-process
(bot, worker, api). The api process serves the single LOCKED ``/v1/metrics``. The
four gauges (``queue_depth``, ``active_workers``, ``db_pool_in_use``,
``redis_connected``) are *live* — the api refreshes them from Redis/DB at scrape
time via :func:`set_live_gauges`, so they are accurate regardless of which process
did the work. When prometheus-client's standard ``PROMETHEUS_MULTIPROC_DIR`` env
var is present (the V1 single-host shared volume) :func:`render` aggregates every
process's counters/histograms; when it is unset (dev/tests) it renders this
process's default registry.
"""

from __future__ import annotations

import os

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client.multiprocess import MultiProcessCollector

CONTENT_TYPE: str = CONTENT_TYPE_LATEST

# --- Counters (Section 15.3) ----------------------------------------------
downloads_total = Counter(
    "downloads_total",
    "Downloads delivered, by platform/format/quality and result.",
    ("platform", "format", "quality", "result"),
)
jobs_created_total = Counter("jobs_created_total", "Download jobs created.")
jobs_completed_total = Counter(
    "jobs_completed_total", "Download jobs finished, by result.", ("result",)
)
cache_hits_total = Counter("cache_hits_total", "Cache hits, by cache.", ("cache",))
cache_misses_total = Counter("cache_misses_total", "Cache misses, by cache.", ("cache",))
ads_shown_total = Counter("ads_shown_total", "Advertisements shown to users.")
broadcasts_sent_total = Counter(
    "broadcasts_sent_total", "Broadcast messages sent, by result.", ("result",)
)
errors_total = Counter("errors_total", "Errors recorded, by type.", ("type",))
# V2.1 shadow-mode cutover gate: the resolver's plan must match the legacy is_premium
# path for every user. Must read 0 over the soak window before V2.2 cutover (V2-D-024).
entitlement_parity_mismatch_total = Counter(
    "entitlement_parity_mismatch_total",
    "Shadow-mode disagreements between the entitlement resolver and the legacy path.",
    ("field",),
)

# --- Histograms (Section 15.3) --------------------------------------------
job_processing_seconds = Histogram(
    "job_processing_seconds", "End-to-end job processing time (seconds)."
)
download_seconds = Histogram("download_seconds", "Provider download time (seconds).")
upload_seconds = Histogram("upload_seconds", "Telegram upload time (seconds).")
telegram_send_seconds = Histogram(
    "telegram_send_seconds", "Telegram send/notify call time (seconds)."
)

# --- Gauges (Section 15.3) — live, refreshed by the api at scrape time -----
# ``livemostrecent`` makes the latest value win under multiprocess aggregation;
# it is ignored in single-process mode.
queue_depth = Gauge("queue_depth", "Jobs waiting in the queue.", multiprocess_mode="livemostrecent")
active_workers = Gauge(
    "active_workers", "Workers with a live heartbeat.", multiprocess_mode="livemostrecent"
)
db_pool_in_use = Gauge(
    "db_pool_in_use",
    "Database connections checked out of the pool.",
    multiprocess_mode="livemostrecent",
)
redis_connected = Gauge(
    "redis_connected",
    "1 if Redis responded to PING, else 0.",
    multiprocess_mode="livemostrecent",
)

# Per-locale translation coverage (V2-D-026), set once at startup by the composition
# root from ``core.i18n.catalog_coverage()``. Computed identically in every process,
# so ``max`` collapses the per-pid series to one under multiprocess aggregation.
i18n_catalog_coverage = Gauge(
    "i18n_catalog_coverage",
    "Fraction of user-facing default-locale keys translated, per locale (0..1).",
    ("locale",),
    multiprocess_mode="max",
)

# Active subscriptions by plan (V2.1). Set at startup / on writes.
subscriptions_active = Gauge(
    "subscriptions_active",
    "Active subscriptions, by plan code.",
    ("plan",),
    multiprocess_mode="livemostrecent",
)


# --- Recording helpers (stable label sets) --------------------------------
def record_download(*, platform: str, format_: str, quality: str, result: str) -> None:
    downloads_total.labels(platform=platform, format=format_, quality=quality, result=result).inc()


def record_job_created() -> None:
    jobs_created_total.inc()


def record_job_completed(result: str) -> None:
    jobs_completed_total.labels(result=result).inc()


def record_cache(cache: str, *, hit: bool) -> None:
    (cache_hits_total if hit else cache_misses_total).labels(cache=cache).inc()


def record_ad_shown() -> None:
    ads_shown_total.inc()


def record_broadcast_sent(result: str, *, count: int = 1) -> None:
    broadcasts_sent_total.labels(result=result).inc(count)


def record_error(error_type: str) -> None:
    errors_total.labels(type=error_type).inc()


def record_entitlement_parity_mismatch(field: str) -> None:
    entitlement_parity_mismatch_total.labels(field=field).inc()


def set_subscriptions_active(counts: dict[str, int]) -> None:
    """Publish active-subscription counts per plan to the gauge (startup / on writes)."""
    for plan, count in counts.items():
        subscriptions_active.labels(plan=plan).set(count)


def observe_job_processing(seconds: float) -> None:
    job_processing_seconds.observe(seconds)


def observe_download(seconds: float) -> None:
    download_seconds.observe(seconds)


def observe_upload(seconds: float) -> None:
    upload_seconds.observe(seconds)


def observe_telegram_send(seconds: float) -> None:
    telegram_send_seconds.observe(seconds)


def set_i18n_coverage(coverage: dict[str, float]) -> None:
    """Publish per-locale translation coverage to the gauge (called once at startup)."""
    for locale, value in coverage.items():
        i18n_catalog_coverage.labels(locale=locale).set(value)


def set_live_gauges(
    *,
    queue_depth_value: int,
    active_workers_value: int,
    db_pool_in_use_value: int,
    redis_connected_value: bool,
) -> None:
    """Set the live gauges to freshly-read values (called by the api at scrape time)."""
    queue_depth.set(queue_depth_value)
    active_workers.set(active_workers_value)
    db_pool_in_use.set(db_pool_in_use_value)
    redis_connected.set(1 if redis_connected_value else 0)


def render() -> tuple[bytes, str]:
    """Return ``(exposition_bytes, content_type)`` for ``/v1/metrics`` (D-050).

    With ``PROMETHEUS_MULTIPROC_DIR`` set, aggregate every process's metrics;
    otherwise render this process's default registry.
    """
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
        return generate_latest(registry), CONTENT_TYPE
    return generate_latest(REGISTRY), CONTENT_TYPE
