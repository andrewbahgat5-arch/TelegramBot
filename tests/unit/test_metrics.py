"""Unit tests for the Prometheus metrics registry (MASTER_PLAN Task 10.2, Section 15.3)."""

from __future__ import annotations

from core import metrics


def _series_names(body: bytes) -> set[str]:
    names: set[str] = set()
    for line in body.decode().splitlines():
        if not line or line.startswith("#"):
            continue
        names.add(line.split("{", 1)[0].split(" ", 1)[0])
    return names


def test_render_returns_prometheus_exposition() -> None:
    body, content_type = metrics.render()
    assert content_type.startswith("text/plain")
    assert b"# HELP" in body


def test_render_exposes_at_least_30_series() -> None:
    # Section 15.3 validation: /v1/metrics returns >= 30 distinct metric series.
    body, _ = metrics.render()
    series = [line for line in body.decode().splitlines() if line and not line.startswith("#")]
    assert len(series) >= 30


def test_recording_helpers_populate_series() -> None:
    metrics.record_download(platform="youtube", format_="video", quality="720p", result="completed")
    metrics.record_job_created()
    metrics.record_job_completed("completed")
    metrics.record_cache("metadata", hit=True)
    metrics.record_cache("metadata", hit=False)
    metrics.record_ad_shown()
    metrics.record_broadcast_sent("ok", count=3)
    metrics.record_error("ExtractionFailedError")
    metrics.observe_job_processing(1.5)
    metrics.observe_download(0.8)
    metrics.observe_upload(0.3)
    metrics.observe_telegram_send(0.1)

    names = _series_names(metrics.render()[0])
    assert "downloads_total" in names
    assert "jobs_created_total" in names
    assert "cache_hits_total" in names
    assert "cache_misses_total" in names
    assert "errors_total" in names
    assert "job_processing_seconds_bucket" in names


def test_live_gauges_reflect_set_values() -> None:
    metrics.set_live_gauges(
        queue_depth_value=7,
        active_workers_value=3,
        db_pool_in_use_value=2,
        redis_connected_value=True,
    )
    body = metrics.render()[0].decode()
    assert "queue_depth 7.0" in body
    assert "active_workers 3.0" in body
    assert "db_pool_in_use 2.0" in body
    assert "redis_connected 1.0" in body

    metrics.set_live_gauges(
        queue_depth_value=0,
        active_workers_value=0,
        db_pool_in_use_value=0,
        redis_connected_value=False,
    )
    assert "redis_connected 0.0" in metrics.render()[0].decode()
