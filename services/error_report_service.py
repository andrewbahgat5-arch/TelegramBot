"""Deliver owner-facing error reports (Sprint 15).

Three things happen to every failure, in this order of importance:

1. **It is logged**, always, with the full traceback and every context field. The log
   file is the complete record; nothing here may cause an exception to be lost.
2. **It is persisted** to ``error_logs`` when a store is wired, so it outlives log
   rotation and stays queryable.
3. **It is sent to the Owner and Moderators** — unless the throttle says this exact
   failure was already reported moments ago.

The ordering matters: reporting must never be able to break the thing it is reporting
on, so every step is individually guarded and the caller is never allowed to see an
exception from this module.

**Routing (DESIGN_MONITORING.md).** Telegram carries CRITICAL only — things needing
intervention now. Everything else is a dashboard row: still logged, still persisted with
full context, simply not pushed to a phone. An alert channel is only useful while every
message in it deserves attention, and the first cut of this system (which pushed every
failure) would have turned one broken extractor into hundreds of messages at target
scale — "notify me about everything" producing *less* awareness, not more.

CRITICAL is additionally never throttled: it is rare by construction and always worth
interrupting for. The throttle below therefore only guards the escape hatch where a
deployment deliberately lowers ``min_severity``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from core.alerting import AlertThrottle
from core.error_report import (
    ErrorReport,
    RequestContext,
    Severity,
    UserContext,
    format_report,
    from_exception,
    report_to_log_fields,
)
from core.logging import get_logger

_log = get_logger("services.error_report")

# How the report reaches staff. Injected so this service stays framework-free: the
# composition root passes AdminNotificationService's fanout (Owner + Moderators).
ReportSink = Callable[[str], Awaitable[None]]
# Optional persistence hook (ErrorLogService.record_failure, pre-bound to a session).
PersistHook = Callable[[BaseException, str], Awaitable[None]]


class ErrorReportService:
    def __init__(
        self,
        sink: ReportSink | None = None,
        *,
        throttle: AlertThrottle | None = None,
        bot_version: str | None = None,
        min_severity: Severity = Severity.CRITICAL,
    ) -> None:
        self._sink = sink
        self._throttle = throttle or AlertThrottle()
        self._bot_version = bot_version
        # CRITICAL-only by default. Lowering this is supported (a staging box may want
        # everything on Telegram) but it is an explicit choice, not the default.
        self._min_severity = min_severity

    async def report_exception(
        self,
        exc: BaseException,
        *,
        severity: Severity,
        kind: str,
        user: UserContext | None = None,
        request: RequestContext | None = None,
        correlation_id: str | None = None,
        include_traceback: bool = True,
        persist: PersistHook | None = None,
    ) -> None:
        report = from_exception(
            exc,
            severity=severity,
            kind=kind,
            user=user,
            request=request,
            correlation_id=correlation_id,
            bot_version=self._bot_version,
            include_traceback=include_traceback,
        )
        await self.deliver(report, persist=persist, exc=exc)

    async def report_event(
        self,
        *,
        severity: Severity,
        kind: str,
        message: str,
        user: UserContext | None = None,
        request: RequestContext | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """A reportable condition with no exception behind it (an unsupported link)."""
        await self.deliver(
            ErrorReport(
                severity=severity,
                kind=kind,
                message=message,
                correlation_id=correlation_id,
                bot_version=self._bot_version,
                user=user,
                request=request,
            )
        )

    async def deliver(
        self,
        report: ErrorReport,
        *,
        persist: PersistHook | None = None,
        exc: BaseException | None = None,
    ) -> None:
        """Log → persist → notify. Never raises."""
        # 1. LOG — unconditional, and first, so a failure in any later step cannot
        # cost us the record. This is the "never lose an exception" guarantee.
        fields = report_to_log_fields(report)
        log = _log.critical if report.severity is Severity.CRITICAL else _log.error
        try:
            if exc is not None:
                log(f"report_{report.kind}", exc_info=exc, **fields)
            else:
                log(f"report_{report.kind}", **fields)
        except Exception:  # noqa: S110 - logging must never propagate
            pass

        # 2. PERSIST — survives log rotation, queryable later.
        if persist is not None and exc is not None:
            try:
                await persist(exc, report.kind)
            except Exception as pexc:
                _log.warning("error_report_persist_failed", error=str(pexc))

        # 3. NOTIFY — the only step that is allowed to be skipped.
        if self._sink is None:
            return
        if _rank(report.severity) < _rank(self._min_severity):
            return
        if report.severity is not Severity.CRITICAL and not self._throttle.should_emit(
            report.fingerprint()
        ):
            _log.debug("error_report_throttled", fingerprint=report.fingerprint())
            return
        try:
            await self._sink(format_report(report))
        except Exception as sexc:
            # A failed alert must not escalate into a second failure. The log entry
            # above already stands as the record.
            _log.warning("error_report_send_failed", kind=report.kind, error=str(sexc))


_SEVERITY_RANK = {
    Severity.INFO: 0,
    Severity.WARNING: 1,
    Severity.ERROR: 2,
    Severity.CRITICAL: 3,
}


def _rank(severity: Severity) -> int:
    return _SEVERITY_RANK.get(severity, 0)
