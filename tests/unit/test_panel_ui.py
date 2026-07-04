"""Unit tests for bot/panel/ui.py — the Dashboard-Grade UI primitives (Sprint 13.1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bot.panel import ui

_AR_TITLE = "تحليلات المنصات"  # "Platform Analytics" in Arabic


# --- header ---------------------------------------------------------------


def test_header_ltr_has_left_marker_bold_title_and_rule() -> None:
    out = ui.header("Platform Analytics")
    assert out.startswith("▸ ")
    assert "<b>Platform Analytics</b>" in out
    assert "\n" in out
    assert out.splitlines()[1] == ui._RULE


def test_header_with_icon_places_icon_before_title() -> None:
    out = ui.header("Stats", icon="📊")
    assert "📊 <b>Stats</b>" in out


def test_header_rtl_uses_right_marker() -> None:
    out = ui.header(_AR_TITLE)
    first_line = out.splitlines()[0]
    assert first_line.endswith("◂")
    assert "▸" not in first_line
    assert f"<b>{_AR_TITLE}</b>" in out


def test_header_escapes_html_in_title() -> None:
    out = ui.header("A <b>x</b> & y")
    assert "&lt;b&gt;x&lt;/b&gt;" in out
    assert "&amp;" in out


# --- divider --------------------------------------------------------------


def test_divider_is_indented_dotted_rule() -> None:
    assert ui.divider() == f"{ui._INDENT}{ui._DIVIDER}"


# --- metric ---------------------------------------------------------------


def test_metric_bolds_value_and_formats_thousands() -> None:
    out = ui.metric("👥", "Members", 1234)
    assert "👥" in out
    assert "Members" in out
    assert "<b>1,234</b>" in out


def test_metric_appends_trend_arrow() -> None:
    out = ui.metric("🆕", "New today", 5, trend="↑")
    assert out.rstrip().endswith("↑")


def test_metric_accepts_string_value_without_reformatting() -> None:
    out = ui.metric("⏱", "Uptime", "3d 4h")
    assert "<b>3d 4h</b>" in out


def test_metric_escapes_label_and_value() -> None:
    out = ui.metric("i", "a & b", "<x>")
    assert "a &amp; b" in out
    assert "&lt;x&gt;" in out


# --- progress_bar ---------------------------------------------------------


def test_progress_bar_zero_total_is_zero_percent() -> None:
    out = ui.progress_bar(5, 0, width=10)
    assert out == f"{ui._EMPTY * 10}  0%"


def test_progress_bar_full() -> None:
    assert ui.progress_bar(10, 10, width=10) == f"{ui._FILL * 10}  100%"


def test_progress_bar_half() -> None:
    out = ui.progress_bar(5, 10, width=10)
    assert out == f"{ui._FILL * 5}{ui._EMPTY * 5}  50%"


def test_progress_bar_clamps_overflow() -> None:
    out = ui.progress_bar(20, 10, width=10)
    assert out == f"{ui._FILL * 10}  100%"


# --- sparkline ------------------------------------------------------------


def test_sparkline_zero_max_is_empty_bar() -> None:
    out = ui.sparkline("YouTube", 0, 0)
    assert ui._FILL not in out
    assert "<b>0</b>" in out


def test_sparkline_proportional_fill() -> None:
    out = ui.sparkline("TikTok", 8, 10, width=10)
    assert ui._FILL * 8 in out
    assert "<b>8</b>" in out


# --- badge ----------------------------------------------------------------


def test_badge_known_states() -> None:
    assert ui.badge("active") == "🟢"
    assert ui.badge("banned") == "🔴"
    assert ui.badge("pending") == "🟡"
    assert ui.badge("inactive") == "⚪"


def test_badge_is_case_insensitive() -> None:
    assert ui.badge("ACTIVE") == "🟢"


def test_badge_unknown_falls_back_to_white_dot() -> None:
    assert ui.badge("nonsense") == "⚪"


# --- card -----------------------------------------------------------------


def test_card_has_bold_title_and_all_fields() -> None:
    out = ui.card("User Profile", [("Name", "Ahmed"), ("ID", "5868066136")])
    assert "◆ <b>User Profile</b>" in out
    assert "Name" in out and "Ahmed" in out
    assert "5868066136" in out


def test_card_escapes_field_values() -> None:
    out = ui.card("T", [("Bio", "<script>&")])
    assert "&lt;script&gt;&amp;" in out


def test_card_custom_icon() -> None:
    out = ui.card("T", [("a", "b")], icon="★")
    assert out.startswith("★ <b>T</b>")


# --- table ----------------------------------------------------------------


def test_table_wraps_in_pre_and_contains_cells() -> None:
    out = ui.table(["#", "Platform", "Count"], [["1", "TikTok", "451"]])
    assert out.startswith("<pre>")
    assert out.endswith("</pre>")
    assert "TikTok" in out
    assert "451" in out


def test_table_right_aligns_numeric_columns() -> None:
    out = ui.table(["Name", "N"], [["Ann", "5"], ["Bob", "100"]])
    # numeric column padded so single digit is right-aligned under the wider cell
    assert "  5" in out


def test_table_escapes_cells() -> None:
    out = ui.table(["H"], [["<x>&"]])
    assert "&lt;x&gt;&amp;" in out


def test_table_with_footer_row() -> None:
    out = ui.table(["P", "N"], [["a", "1"]], footer=["Total", "1"])
    assert "Total" in out


# --- footer ---------------------------------------------------------------


def test_footer_formats_given_utc_time() -> None:
    dt = datetime(2026, 7, 4, 12, 30, tzinfo=UTC)
    assert ui.footer(dt) == f"{ui._INDENT}∙ Updated 12:30 UTC ∙"


def test_footer_treats_naive_as_utc() -> None:
    dt = datetime(2026, 7, 4, 9, 5)
    assert "09:05 UTC" in ui.footer(dt)


def test_footer_none_returns_a_line() -> None:
    assert "Updated" in ui.footer()


# --- status_dot / role_icon ----------------------------------------------


def test_status_dot() -> None:
    assert ui.status_dot(True) == "🟢"
    assert ui.status_dot(False) == "🔴"


def test_role_icon_mapping() -> None:
    assert ui.role_icon("owner") == "👑"
    assert ui.role_icon("moderator") == "🛡"
    assert ui.role_icon("premium") == "⭐"
    assert ui.role_icon("user") == "👤"
    assert ui.role_icon("unknown") == "👤"


# --- number_fmt -----------------------------------------------------------


def test_number_fmt() -> None:
    assert ui.number_fmt(1234) == "1,234"
    assert ui.number_fmt(0) == "0"
    assert ui.number_fmt(-1234567) == "-1,234,567"
    assert ui.number_fmt(999) == "999"


# --- time_ago -------------------------------------------------------------


def _ago(**kw: float) -> datetime:
    return datetime.now(UTC) - timedelta(**kw)


def test_time_ago_just_now() -> None:
    assert ui.time_ago(_ago(seconds=5)) == "just now"


def test_time_ago_minutes() -> None:
    assert ui.time_ago(_ago(minutes=5)) == "5 min ago"


def test_time_ago_single_hour() -> None:
    assert ui.time_ago(_ago(hours=1, minutes=1)) == "1 hour ago"


def test_time_ago_hours() -> None:
    assert ui.time_ago(_ago(hours=3)) == "3 hours ago"


def test_time_ago_yesterday() -> None:
    assert ui.time_ago(_ago(days=1, hours=2)) == "yesterday"


def test_time_ago_days() -> None:
    assert ui.time_ago(_ago(days=5)) == "5 days ago"


def test_time_ago_months() -> None:
    assert ui.time_ago(_ago(days=60)) == "2 months ago"


def test_time_ago_years() -> None:
    assert ui.time_ago(_ago(days=400)) == "1 year ago"


def test_time_ago_future_is_just_now() -> None:
    future = datetime.now(UTC) + timedelta(hours=1)
    assert ui.time_ago(future) == "just now"


def test_time_ago_naive_assumed_utc() -> None:
    naive = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=10)
    assert ui.time_ago(naive) == "10 min ago"
