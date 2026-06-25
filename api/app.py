"""FastAPI application factory (MASTER_PLAN Task 10.2 / 10.4, Section 20.2, D-049).

Serves the three public V1 endpoints — ``/v1/health`` (liveness), ``/v1/ready``
(readiness, Section 15.7) and ``/v1/metrics`` (Prometheus, Section 15.3). The admin
surface (Task 8.3) is intentionally absent and stays deferred. This module depends
only on ``core``/``api`` (no infrastructure); the composition root ``api/main.py``
injects the readiness checker and the metrics refresh hook.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Response

from api.readiness import ReadinessChecker
from core import metrics

RefreshMetrics = Callable[[], Awaitable[None]]


def create_app(
    *,
    checker: ReadinessChecker,
    refresh_metrics: RefreshMetrics,
) -> FastAPI:
    """Build the FastAPI app for the api process."""
    app = FastAPI(title="Telegram Download Bot API", version="1", docs_url=None, redoc_url=None)

    @app.get("/v1/health")
    async def health() -> dict[str, str]:
        """Liveness: the process is up and serving (Section 15.7)."""
        return {"status": "ok"}

    @app.get("/v1/ready")
    async def ready(response: Response) -> dict[str, object]:
        """Readiness: DB + Redis + queue + worker checks (Section 15.7)."""
        report = await checker.check()
        if not report.ready:
            response.status_code = 503
        return {
            "ready": report.ready,
            "checks": {
                name: {"ok": result.ok, "detail": result.detail}
                for name, result in report.checks.items()
            },
        }

    @app.get("/v1/metrics")
    async def metrics_endpoint() -> Response:
        """Prometheus exposition (Section 15.3). Live gauges are refreshed first."""
        await refresh_metrics()
        body, content_type = metrics.render()
        return Response(content=body, media_type=content_type)

    return app
