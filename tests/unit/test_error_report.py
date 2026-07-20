"""Owner error reports: formatting, escaping, size limits, and delivery guarantees."""

from __future__ import annotations

from core.alerting import AlertThrottle
from core.error_report import (
    ErrorReport,
    RequestContext,
    Severity,
    UserContext,
    condense_traceback,
    format_report,
    from_exception,
    origin_of,
)
from services.error_report_service import ErrorReportService

_USER = UserContext(
    telegram_id=555,
    username="someone",
    first_name="Sam",
    last_name="Doe",
    chat_id=999,
    chat_type="private",
    language="ar",
    is_premium=True,
    plan="free",
    action="/start",
)
_REQ = RequestContext(
    url="https://www.instagram.com/p/ABC/",
    platform="instagram",
    media_type="video",
    quality="1080p",
    stage="download",
    duration_ms=1234,
    worker_id="w-3",
    cache_hit=False,
)


def _boom() -> BaseException:
    try:
        raise ValueError("it exploded")
    except ValueError as exc:
        return exc


def test_report_contains_every_requested_section() -> None:
    text = format_report(
        from_exception(
            _boom(), severity=Severity.ERROR, kind="download_failed",
            user=_USER, request=_REQ, correlation_id="abc-123",
        )
    )
    for expected in ("👤 User", "🔗 URL", "📄 Request", "⚠️ Error", "🕒 Time", "📚 Stack trace"):
        assert expected in text
    assert "ERROR" in text and "🟠" in text
    assert "@someone" in text and "Sam Doe" in text
    assert "https://www.instagram.com/p/ABC/" in text
    assert "1080p" in text and "download" in text and "w-3" in text
    assert "ValueError" in text and "it exploded" in text
    assert "abc-123" in text


def test_severity_emojis_are_distinct() -> None:
    emojis = {s.emoji for s in Severity}
    assert emojis == {"🔴", "🟠", "🟡", "🔵"}
    assert len(emojis) == 4


def test_html_in_user_content_is_escaped() -> None:
    """Usernames, titles and URLs are stranger-controlled and the report is HTML —
    an unescaped '<' would break the message or inject markup."""
    report = ErrorReport(
        severity=Severity.WARNING,
        kind="unsupported_url",
        message="nope",
        user=UserContext(telegram_id=1, username="<b>pwn</b>"),
        request=RequestContext(url="https://x.test/<script>alert(1)</script>"),
    )
    text = format_report(report)
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "<b>pwn</b>" not in text


def test_empty_fields_are_omitted_not_rendered_as_none() -> None:
    text = format_report(
        ErrorReport(severity=Severity.INFO, kind="x", message="m", user=UserContext(telegram_id=7))
    )
    assert "None" not in text


def test_message_always_fits_telegram_limit() -> None:
    """A 4096-char overflow makes Telegram reject the whole report. A clipped alert
    beats a dropped one, so the stack trace gives way — never the context."""
    huge = "\n".join(f'  File "/app/mod{i}.py", line {i}, in fn{i}' for i in range(4000))
    report = ErrorReport(
        severity=Severity.CRITICAL,
        kind="crash",
        exc_type="RuntimeError",
        message="x" * 300,
        traceback_text=huge,
        user=_USER,
        request=_REQ,
    )
    text = format_report(report)
    assert len(text) <= 4096
    assert "👤 User" in text  # context survived
    assert "🔗 URL" in text


def test_condense_traceback_keeps_head_and_tail() -> None:
    """The last frames say what broke; the first say where it entered. The middle is
    what gets dropped."""
    lines = [f"line{i}" for i in range(60)]
    out = condense_traceback("\n".join(lines))
    assert "line0" in out and "line59" in out
    assert "frames omitted" in out
    assert len(out.splitlines()) < 60


def test_origin_points_at_the_deepest_frame() -> None:
    """Where it actually broke, not where it was caught."""
    origin = origin_of(_boom())
    assert origin["function"] == "_boom"
    assert origin["line"]
    assert origin["module"]


def test_fingerprint_ignores_user_and_exact_url() -> None:
    """One broken extractor hit by 200 users must be ONE alert, not 200."""
    def make(uid: int, path: str) -> ErrorReport:
        return ErrorReport(
            severity=Severity.ERROR, kind="extract_failed", exc_type="ExtractionFailedError",
            user=UserContext(telegram_id=uid),
            request=RequestContext(
                url=f"https://www.instagram.com/p/{path}/", platform="instagram"
            ),
        )
    assert make(1, "AAA").fingerprint() == make(2, "BBB").fingerprint()


def test_fingerprint_separates_different_platforms() -> None:
    a = ErrorReport(severity=Severity.ERROR, kind="k", exc_type="E",
                    request=RequestContext(url="https://a.test/x", platform="a"))
    b = ErrorReport(severity=Severity.ERROR, kind="k", exc_type="E",
                    request=RequestContext(url="https://b.test/x", platform="b"))
    assert a.fingerprint() != b.fingerprint()


# --- delivery guarantees ---------------------------------------------------
class _Sink:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[str] = []
        self._fail = fail

    async def __call__(self, text: str) -> None:
        if self._fail:
            raise RuntimeError("telegram is down")
        self.sent.append(text)


async def test_only_critical_reaches_telegram_by_default() -> None:
    """DESIGN_MONITORING.md: Telegram carries critical events only. Everything else is
    a dashboard row — still logged, still persisted, simply not pushed to a phone. An
    alert channel is only useful while every message in it deserves attention."""
    sink = _Sink()
    svc = ErrorReportService(sink)
    await svc.report_event(severity=Severity.INFO, kind="unsupported_url", message="m")
    await svc.report_exception(_boom(), severity=Severity.WARNING, kind="w")
    await svc.report_exception(_boom(), severity=Severity.ERROR, kind="extract_failed")
    assert sink.sent == []  # nothing pushed
    await svc.report_exception(_boom(), severity=Severity.CRITICAL, kind="db_unavailable")
    assert len(sink.sent) == 1  # only the critical one


async def test_duplicate_failures_are_throttled_to_one_message() -> None:
    """The escape hatch: a deployment may lower min_severity (staging often does), and
    the throttle then collapses identical failures so one broken extractor hit by many
    users is still one message."""
    sink = _Sink()
    svc = ErrorReportService(
        sink, throttle=AlertThrottle(window_seconds=300), min_severity=Severity.ERROR
    )
    for uid in range(5):
        await svc.report_exception(
            _boom(), severity=Severity.ERROR, kind="extract_failed",
            user=UserContext(telegram_id=uid),
            request=RequestContext(url="https://x.test/a", platform="x"),
        )
    assert len(sink.sent) == 1  # same fingerprint → one alert


async def test_critical_bypasses_the_throttle() -> None:
    """A crash is rare and always worth interrupting for."""
    sink = _Sink()
    svc = ErrorReportService(sink, throttle=AlertThrottle(window_seconds=300))
    for _ in range(3):
        await svc.report_exception(_boom(), severity=Severity.CRITICAL, kind="crash")
    assert len(sink.sent) == 3


async def test_a_failing_sink_never_propagates() -> None:
    """Reporting must not be able to break the thing it is reporting on."""
    svc = ErrorReportService(_Sink(fail=True))
    await svc.report_exception(_boom(), severity=Severity.CRITICAL, kind="crash")


async def test_persist_failure_still_sends_and_never_raises() -> None:
    sink = _Sink()

    async def bad_persist(_exc: BaseException, _kind: str) -> None:
        raise RuntimeError("db down")

    svc = ErrorReportService(sink)
    await svc.report_exception(
        _boom(), severity=Severity.CRITICAL, kind="crash", persist=bad_persist
    )
    assert len(sink.sent) == 1  # the DB being down must not cost us the alert


async def test_min_severity_filters_the_channel() -> None:
    sink = _Sink()
    svc = ErrorReportService(sink, min_severity=Severity.ERROR)
    await svc.report_event(severity=Severity.INFO, kind="unsupported_url", message="m")
    assert sink.sent == []
    await svc.report_exception(_boom(), severity=Severity.ERROR, kind="boom")
    assert len(sink.sent) == 1


async def test_works_with_no_sink_configured() -> None:
    """No Telegram wiring (tests, a bare deployment) must still log and not raise."""
    await ErrorReportService(None).report_exception(
        _boom(), severity=Severity.ERROR, kind="boom"
    )
