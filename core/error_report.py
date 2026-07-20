"""Owner-facing error reports (Sprint 15).

Turns a failure plus its context into one scannable Telegram message, so an operator
can diagnose most problems without opening the server. Pure: no I/O, no framework
imports — the sending lives in ``services/error_report_service.py`` and the transport
in ``infrastructure``. That split keeps the formatting exhaustively unit-testable,
which matters because these messages are only ever read when something is already
going wrong.

Two deliberate decisions worth knowing about:

**Full URLs appear here.** Everywhere else the codebase records only
``platform``/``url_host``/``url_hash`` and keeps user URLs out of the logs. Reports go
to the Owner and Moderators only, and an unsupported-URL report is worthless without
the link that failed — an operator has to be able to paste it back in. The trade is
explicit: these messages, and the ``error_logs`` rows behind them, do contain user
content.

**Everything is escaped and truncated.** Usernames, titles and URLs are attacker- (or
at least stranger-) controlled, and the report is HTML. Telegram also hard-caps a
message at 4096 characters, so a long stack trace must lose its middle rather than
have the API reject the whole report — a dropped alert is worse than a clipped one.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import traceback as _tb
from dataclasses import dataclass, field
from enum import StrEnum
from html import escape
from typing import Any

# Telegram's hard limit is 4096; leave room for the closing of a truncated section.
TELEGRAM_MESSAGE_LIMIT = 4096
_SAFE_LIMIT = 3900
_TRACE_HEAD_LINES = 6
_TRACE_TAIL_LINES = 14


class Severity(StrEnum):
    """How loud this is. Not everything that fails is an emergency — a user pasting a
    link we do not support is information, not a crash, and treating it as one trains
    the operator to ignore the channel."""

    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def emoji(self) -> str:
        return {
            Severity.CRITICAL: "🔴",
            Severity.ERROR: "🟠",
            Severity.WARNING: "🟡",
            Severity.INFO: "🔵",
        }[self]

    @property
    def label(self) -> str:
        return {
            Severity.CRITICAL: "CRITICAL",
            Severity.ERROR: "ERROR",
            Severity.WARNING: "WARNING",
            Severity.INFO: "INFO",
        }[self]


@dataclass(frozen=True, slots=True)
class UserContext:
    """Who hit it. Every field optional — a worker crash has no user."""

    telegram_id: int | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    chat_id: int | None = None
    chat_type: str | None = None  # "private" | "group" | "supergroup" | "channel"
    language: str | None = None
    is_premium: bool | None = None
    plan: str | None = None
    action: str | None = None  # the command/step in flight


@dataclass(frozen=True, slots=True)
class RequestContext:
    """What was being attempted."""

    url: str | None = None
    platform: str | None = None
    media_type: str | None = None
    quality: str | None = None
    format: str | None = None
    item_index: int | None = None
    stage: str | None = None  # analyze / download / transcode / upload
    duration_ms: int | None = None
    queue_id: str | None = None
    job_id: str | None = None
    worker_id: str | None = None
    cache_hit: bool | None = None


@dataclass(frozen=True, slots=True)
class ErrorReport:
    """One failure, fully described."""

    severity: Severity
    kind: str  # short machine-ish label, e.g. "unsupported_url", "worker_crash"
    exc_type: str | None = None
    message: str | None = None
    traceback_text: str | None = None
    module: str | None = None
    function: str | None = None
    file: str | None = None
    line: int | None = None
    correlation_id: str | None = None
    bot_version: str | None = None
    timestamp: _dt.datetime = field(
        default_factory=lambda: _dt.datetime.now(_dt.UTC)
    )
    user: UserContext | None = None
    request: RequestContext | None = None

    def fingerprint(self) -> str:
        """Identity for throttling: the same bug on the same site collapses to one alert.

        Deliberately excludes the user and the exact URL — otherwise a single broken
        extractor hit by 200 people would send 200 "new" alerts, which is precisely the
        flood the throttle exists to stop.
        """
        host = ""
        if self.request and self.request.url:
            host = _host_of(self.request.url)
        platform = self.request.platform if self.request else ""
        parts = [self.kind, self.exc_type or "", platform or "", host]
        return "|".join(p or "-" for p in parts)


def _host_of(url: str) -> str:
    from urllib.parse import urlparse

    try:
        return urlparse(url.strip()).netloc.lower()
    except ValueError:
        return ""


def _e(value: Any) -> str:
    """HTML-escape any value for inclusion in the report."""
    return escape(str(value), quote=False)


def _row(label: str, value: Any) -> str | None:
    """One `label: value` line, or None when there is nothing to say.

    Empty fields are omitted rather than rendered as "None" — a report padded with
    placeholders is harder to scan, which defeats the point.
    """
    if value is None or value == "":
        return None
    return f"{label}: <code>{_e(value)}</code>"


def _section(title: str, rows: list[str | None]) -> str:
    body = [r for r in rows if r]
    if not body:
        return ""
    return f"<b>{title}</b>\n" + "\n".join(body)


def condense_traceback(
    text: str, *, head: int = _TRACE_HEAD_LINES, tail: int = _TRACE_TAIL_LINES
) -> str:
    """Keep the start and the END of a traceback, drop the middle.

    The last frames say what actually blew up and the first say where it entered, so a
    deep recursion or a long framework stack loses only the uninformative middle.
    """
    lines = [ln.rstrip() for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) <= head + tail:
        return "\n".join(lines)
    omitted = len(lines) - head - tail
    return "\n".join([*lines[:head], f"… {omitted} frames omitted …", *lines[-tail:]])


def traceback_of(exc: BaseException) -> str:
    return "".join(_tb.format_exception(type(exc), exc, exc.__traceback__))


def origin_of(exc: BaseException) -> dict[str, Any]:
    """Module / function / file / line of the DEEPEST frame — where it actually broke,
    not where it was caught."""
    tb = exc.__traceback__
    if tb is None:
        return {}
    last = tb
    while last.tb_next is not None:
        last = last.tb_next
    frame = last.tb_frame
    return {
        "module": frame.f_globals.get("__name__"),
        "function": frame.f_code.co_name,
        "file": frame.f_code.co_filename,
        "line": last.tb_lineno,
    }


def from_exception(
    exc: BaseException,
    *,
    severity: Severity,
    kind: str,
    user: UserContext | None = None,
    request: RequestContext | None = None,
    correlation_id: str | None = None,
    bot_version: str | None = None,
    include_traceback: bool = True,
) -> ErrorReport:
    """Build a report from a live exception, capturing where it really failed."""
    origin = origin_of(exc)
    return ErrorReport(
        severity=severity,
        kind=kind,
        exc_type=type(exc).__name__,
        message=str(exc) or type(exc).__name__,
        traceback_text=traceback_of(exc) if include_traceback else None,
        module=origin.get("module"),
        function=origin.get("function"),
        file=origin.get("file"),
        line=origin.get("line"),
        correlation_id=correlation_id,
        bot_version=bot_version,
        user=user,
        request=request,
    )


def format_report(report: ErrorReport) -> str:
    """Render the report as Telegram HTML, guaranteed to fit in one message.

    Sections are ordered by what an operator reads first: what broke, then who hit it,
    then the link, then the request, then the error, then the stack.
    """
    ts = report.timestamp.astimezone(_dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    header = (
        f"{report.severity.emoji} <b>{_e(report.severity.label)}</b> — "
        f"<code>{_e(report.kind)}</code>"
    )

    sections: list[str] = [header]

    u = report.user
    if u is not None:
        name = " ".join(p for p in (u.first_name, u.last_name) if p)
        sections.append(
            _section(
                "👤 User",
                [
                    _row("ID", u.telegram_id),
                    _row("Username", f"@{u.username}" if u.username else None),
                    _row("Name", name),
                    _row("Chat", u.chat_id),
                    _row("Chat type", u.chat_type),
                    _row("Language", u.language),
                    _row("Premium", u.is_premium if u.is_premium is not None else None),
                    _row("Plan", u.plan),
                    _row("Action", u.action),
                ],
            )
        )

    r = report.request
    if r is not None:
        if r.url:
            sections.append(f"<b>🔗 URL</b>\n<code>{_e(r.url)}</code>")
        sections.append(
            _section(
                "📄 Request",
                [
                    _row("Platform", r.platform),
                    _row("Media", r.media_type),
                    _row("Item", r.item_index),
                    _row("Quality", r.quality),
                    _row("Format", r.format),
                    _row("Stage", r.stage),
                    _row("Took", f"{r.duration_ms} ms" if r.duration_ms is not None else None),
                    _row("Job", r.job_id),
                    _row("Queue", r.queue_id),
                    _row("Worker", r.worker_id),
                    _row(
                        "Cache",
                        None if r.cache_hit is None else ("hit" if r.cache_hit else "miss"),
                    ),
                ],
            )
        )

    sections.append(
        _section(
            "⚠️ Error",
            [
                _row("Type", report.exc_type),
                _row("Message", report.message),
                _row("Module", report.module),
                _row("Function", report.function),
                _row("Line", f"{report.file}:{report.line}" if report.file else None),
                _row("Correlation", report.correlation_id),
                _row("Version", report.bot_version),
            ],
        )
    )
    sections.append(f"<b>🕒 Time</b>\n<code>{_e(ts)}</code>")

    body = "\n\n".join(s for s in sections if s)

    if report.traceback_text:
        trace = condense_traceback(report.traceback_text)
        block = f"\n\n<b>📚 Stack trace</b>\n<pre>{_e(trace)}</pre>"
        # Shrink the trace until the whole message fits; the context above it is more
        # valuable than the middle of the stack, so the stack is what gives way.
        while len(body) + len(block) > _SAFE_LIMIT and "\n" in trace:
            trace = "\n".join(trace.splitlines()[1:])
            block = f"\n\n<b>📚 Stack trace</b>\n<pre>{_e(trace)}</pre>"
        if len(body) + len(block) <= _SAFE_LIMIT:
            body += block

    if len(body) > TELEGRAM_MESSAGE_LIMIT:
        body = body[: TELEGRAM_MESSAGE_LIMIT - 20] + "\n… truncated …"
    return body


def report_to_log_fields(report: ErrorReport) -> dict[str, Any]:
    """Flatten for structured logging, so the log file keeps everything the Telegram
    message had to abbreviate. Telegram is for awareness; the log is the record."""
    fields: dict[str, Any] = {
        "severity": report.severity.value,
        "kind": report.kind,
        "exc_type": report.exc_type,
        "error_message": report.message,
        "module": report.module,
        "function": report.function,
        "file": report.file,
        "line": report.line,
        "correlation_id": report.correlation_id,
    }
    if report.user is not None:
        fields.update(
            {f"user_{k}": v for k, v in dataclasses.asdict(report.user).items() if v is not None}
        )
    if report.request is not None:
        fields.update(
            {f"req_{k}": v for k, v in dataclasses.asdict(report.request).items() if v is not None}
        )
    return {k: v for k, v in fields.items() if v is not None}
