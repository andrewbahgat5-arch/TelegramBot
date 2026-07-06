"""Admin-panel UI primitives — the "Dashboard Grade" design system (Sprint 13.1).

A *pure* presentation module: every function returns a Telegram-HTML string and
performs no I/O, no service calls, no database access. All admin-panel screens
render through these helpers so the look is consistent and defined in exactly one
place (SPRINT_13_PLAN §2), instead of ad-hoc emoji-in-a-wall-of-text formatting.

Design rules honoured here:

* **HTML parse mode** — bold is ``<b>``, italic ``<i>``, monospace ``<pre>`` /
  ``<code>``. Every piece of *dynamic* content (titles, labels, values, table
  cells) is passed through :func:`html.escape` so a stray ``<`` / ``&`` from a
  username or setting can never break the message or inject markup.
* **Locale-aware / RTL** — the helpers infer text direction from the content
  (:func:`_is_rtl`, Arabic/Hebrew ranges) rather than taking a locale argument,
  keeping the signatures in the plan intact. Latin and Arabic both render cleanly.
* **Approximate columnar layout** — following the plan's own note on the card
  primitive, we align with padding spaces (not brittle box-drawing) except for
  :func:`table`, which is the one primitive that genuinely needs a monospace
  ``<pre>`` block.

Labels reach these functions *already translated* (the caller resolves the
``core.i18n`` key first) — this module never touches the catalog.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from html import escape

# --- Glyph & layout constants ---------------------------------------------
# Kept narrow enough to render without wrapping on a phone in either direction.

_INDENT = "  "
_RULE = "╌" * 22
_DIVIDER = "┈" * 17
_FILL = "▰"
_EMPTY = "▱"
_LEFT_MARKER = "▸"
_RIGHT_MARKER = "◂"
# RIGHT-TO-LEFT MARK (U+200F) — anchors an RTL line's base direction. Intentional
# and required for correct Arabic rendering; bandit's trojan-source (B613) check
# flags any bidi control char, so it is suppressed here with justification.
_RLM = "‏"  # nosec B613

_METRIC_LABEL_WIDTH = 16
_METRIC_VALUE_WIDTH = 6
_SPARK_LABEL_WIDTH = 12
_CARD_LABEL_WIDTH = 11

# --- Semantic emoji registry (animation-ready, Sprint 13) -----------------
# Every icon the panel uses is named by a semantic code with a Unicode fallback.
# Routing all icons through emoji(code) lets a single map — CUSTOM_EMOJI_IDS —
# switch the whole panel to *animated* Telegram custom emoji the moment the bot
# has a Fragment-purchased username and the custom_emoji_ids are known (custom
# emoji entities are otherwise rejected by the Bot API). Until then every code
# renders as its plain Unicode fallback, so nothing changes for a normal bot.
_EMOJI: dict[str, str] = {
    # dashboard / metrics
    "members": "👥",
    "new": "🆕",
    "active": "⚡",
    "fire": "🔥",
    "sleep": "💤",
    "download": "📥",
    "queue": "⚡",
    "clock": "⏱",
    "calendar": "📅",
    "chart": "📊",
    # roles / status
    "premium": "⭐",
    "owner": "👑",
    "moderator": "🛡",
    "user": "👤",
    "blocked": "🚫",
    "deleted": "💀",
    # colour dots
    "dot_green": "🟢",
    "dot_red": "🔴",
    "dot_yellow": "🟡",
    "dot_white": "⚪",
    "dot_blue": "🔵",
    # section icons
    "users": "👥",
    "stats": "📊",
    "broadcast": "📢",
    "ads": "🎯",
    "referral": "🔗",
    "moderation": "🛡",
    "settings": "⚙️",
    "templates": "📝",
    "system": "🖥",
    "language": "🌐",
    "history": "🗂",
    "queue_section": "💾",
    # action icons
    "back": "⬅️",
    "close": "❌",
    "refresh": "🔄",
    "export": "📤",
    "import": "📥",
    "edit": "✏️",
    "trash": "🗑",
    "check": "✅",
    "cross": "❌",
    "search": "🔍",
    "gift": "🎁",
    "trophy": "🏆",
    "party": "🎉",
    "hourglass": "⏳",
    "doc": "📄",
    "note": "📝",
    "warn": "⚠️",
    "link": "🔗",
    "share": "📤",
    "recycle": "♻️",
}

# code -> Telegram custom_emoji_id. EMPTY until the bot has a Fragment username
# and the animated custom-emoji ids are known; fill this to switch on animation.
CUSTOM_EMOJI_IDS: dict[str, str] = {}

# Semantic state -> emoji code for badges (SPRINT_13_PLAN §2.3). Unknown → ⚪.
_BADGE_CODES = {
    "active": "dot_green",
    "banned": "dot_red",
    "disabled": "dot_red",
    "pending": "dot_yellow",
    "warning": "dot_yellow",
    "inactive": "dot_white",
    "empty": "dot_white",
    "premium": "premium",
    "owner": "owner",
    "moderator": "moderator",
    "blocked": "blocked",
    "deleted": "deleted",
}

_ROLE_CODES = {
    "owner": "owner",
    "moderator": "moderator",
    "premium": "premium",
    "user": "user",
}

_NUMERIC_CELL = re.compile(r"^\d[\d,.%-]*$")  # digit-led: digits, comma, dot, %, minus


# --- Direction & escaping helpers -----------------------------------------

_RTL_RANGES = (
    (0x0590, 0x05FF),  # Hebrew
    (0x0600, 0x06FF),  # Arabic
    (0x0750, 0x077F),  # Arabic Supplement
    (0x08A0, 0x08FF),  # Arabic Extended-A
    (0xFB50, 0xFDFF),  # Arabic Presentation Forms-A
    (0xFE70, 0xFEFF),  # Arabic Presentation Forms-B
)


def _is_rtl(text: str) -> bool:
    """True if ``text`` contains any right-to-left (Arabic/Hebrew) character."""
    for ch in text:
        code = ord(ch)
        for low, high in _RTL_RANGES:
            if low <= code <= high:
                return True
    return False


def _esc(text: str) -> str:
    """HTML-escape dynamic content (quote=False keeps quotes readable in prose)."""
    return escape(text, quote=False)


def _fmt_value(value: int | str) -> str:
    """Render a metric value: ints get thousands separators, strings pass through."""
    return number_fmt(value) if isinstance(value, int) else value


# --- Public primitives -----------------------------------------------------


def emoji(code: str) -> str:
    """Render a semantic emoji code (SPRINT_13 animation-ready layer).

    Returns an animated ``<tg-emoji>`` custom emoji when the code has an entry in
    :data:`CUSTOM_EMOJI_IDS`, otherwise the plain Unicode fallback. An unknown
    code yields an empty string (never raises), so a typo degrades quietly rather
    than crashing a screen render.
    """
    fallback = _EMOJI.get(code, "")
    custom_id = CUSTOM_EMOJI_IDS.get(code)
    if custom_id and fallback:
        return f'<tg-emoji emoji-id="{_esc(custom_id)}">{_esc(fallback)}</tg-emoji>'
    return fallback


def header(title: str, icon: str | None = None) -> str:
    """A screen title with a thin rule beneath it (SPRINT_13_PLAN §2.1).

    The direction marker sits left of the title in LTR and right of it in RTL, so
    an Arabic title reads correctly without the caller passing a locale.
    """
    title_html = f"<b>{_esc(title)}</b>"
    icon_part = f"{_esc(icon)} " if icon else ""
    if _is_rtl(title):
        line = f"{_RLM}{title_html} {icon_part}{_RIGHT_MARKER}".rstrip()
    else:
        line = f"{_LEFT_MARKER} {icon_part}{title_html}"
    return f"{line}\n{_RULE}"


def divider() -> str:
    """A light break between logical groups inside one screen (not a header)."""
    return f"{_INDENT}{_DIVIDER}"


def metric(icon: str, label: str, value: int | str, trend: str | None = None) -> str:
    """A single stat line: dimmed label, bold value, optional trend arrow.

    ``value`` ints are formatted with thousands separators. The value is padded
    to a small column so a stack of ``metric()`` lines reads as a table.
    """
    label_cell = _esc(label.ljust(_METRIC_LABEL_WIDTH))
    value_str = _fmt_value(value)
    pad = " " * max(0, _METRIC_VALUE_WIDTH - len(value_str))
    trend_part = f"  {_esc(trend)}" if trend else ""
    return f"{_INDENT}{_esc(icon)}  {label_cell}{pad}<b>{_esc(value_str)}</b>{trend_part}"


def progress_bar(current: int, total: int, width: int = 10) -> str:
    """A horizontal fill bar with an inline percentage (0% when ``total`` <= 0)."""
    width = max(1, width)
    if total <= 0:
        ratio = 0.0
    else:
        ratio = min(1.0, max(0.0, current / total))
    filled = round(ratio * width)
    bar = f"{_FILL * filled}{_EMPTY * (width - filled)}"
    return f"{bar}  {round(ratio * 100)}%"


def sparkline(label: str, value: int, max_value: int, width: int = 10) -> str:
    """A metric line with an inline proportional bar (value relative to a max)."""
    width = max(1, width)
    if max_value <= 0:
        filled = 0
    else:
        filled = round(min(1.0, max(0.0, value / max_value)) * width)
    bar = f"{_FILL * filled}{_EMPTY * (width - filled)}"
    label_cell = _esc(label.ljust(_SPARK_LABEL_WIDTH))
    value_str = number_fmt(value)
    pad = " " * max(0, _METRIC_VALUE_WIDTH - len(value_str))
    return f"{_INDENT}{label_cell}{bar}{pad}<b>{value_str}</b>"


def badge(state: str) -> str:
    """Map a semantic state name to a colour-dot emoji (unknown → ⚪)."""
    return emoji(_BADGE_CODES.get(state.lower(), "dot_white"))


def card(title: str, fields: list[tuple[str, str]], icon: str = "◆") -> str:
    """A titled block of ``(label, value)`` rows — the Detail-screen primitive.

    Uses the plan's device-safe layout (bold title + indented, padded fields)
    rather than box-drawing that renders inconsistently across Telegram clients.
    """
    lines = [f"{_esc(icon)} <b>{_esc(title)}</b>", ""]
    for label, value in fields:
        label_cell = _esc(label.ljust(_CARD_LABEL_WIDTH))
        lines.append(f"{_INDENT}{label_cell}{_esc(value)}")
    return "\n".join(lines)


def table(headers: list[str], rows: list[list[str]], footer: list[str] | None = None) -> str:
    """A monospace ``<pre>`` table with per-column width and numeric right-align.

    A column is right-aligned when every one of its body cells looks numeric
    (digits plus ``, . - %``); otherwise it is left-aligned. Cell contents are
    escaped; column widths are computed on the raw (pre-escape) text so the
    rendered glyphs still line up.
    """
    all_rows = [headers, *rows] + ([footer] if footer is not None else [])
    col_count = max((len(r) for r in all_rows), default=0)
    widths = [0] * col_count
    for row in all_rows:
        for c in range(col_count):
            cell = row[c] if c < len(row) else ""
            widths[c] = max(widths[c], len(cell))

    right_align = [
        bool(rows) and all(c < len(row) and _looks_numeric(row[c]) for row in rows)
        for c in range(col_count)
    ]

    def fmt_row(row: list[str]) -> str:
        cells = []
        for c in range(col_count):
            cell = row[c] if c < len(row) else ""
            padded = cell.rjust(widths[c]) if right_align[c] else cell.ljust(widths[c])
            cells.append(_esc(padded))
        return "  ".join(cells).rstrip()

    sep = "─" * (sum(widths) + 2 * max(0, col_count - 1))
    body = [fmt_row(headers), sep]
    body.extend(fmt_row(r) for r in rows)
    if footer is not None:
        body.append(sep)
        body.append(fmt_row(footer))
    return "<pre>" + "\n".join(body) + "</pre>"


def footer(timestamp: datetime | None = None) -> str:
    """A subtle ``∙ Updated HH:MM UTC ∙`` metadata line (defaults to now)."""
    dt = timestamp or datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return f"{_INDENT}∙ Updated {dt:%H:%M} UTC ∙"


def status_dot(enabled: bool) -> str:
    """Boolean state as a colour dot: 🟢 enabled / 🔴 disabled."""
    return emoji("dot_green") if enabled else emoji("dot_red")


def role_icon(role: str) -> str:
    """Map a role name to its icon (owner 👑, moderator 🛡, premium ⭐, user 👤)."""
    return emoji(_ROLE_CODES.get(role.lower(), "user"))


def number_fmt(n: int) -> str:
    """Format an integer with thousands separators: ``1234`` → ``"1,234"``."""
    return f"{n:,}"


def time_ago(dt: datetime) -> str:
    """A coarse relative-time label ("just now", "5 min ago", "yesterday", …).

    Compared against the current UTC time; a naive ``dt`` is assumed to be UTC.
    Future timestamps collapse to "just now" (clock skew, not an error).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    seconds = (now - dt).total_seconds()
    if seconds < 0:
        seconds = 0
    minutes = seconds / 60
    hours = minutes / 60
    days = hours / 24
    if seconds < 45:
        return "just now"
    if minutes < 60:
        n = max(1, round(minutes))
        return f"{n} min ago"
    if hours < 24:
        n = round(hours)
        return "1 hour ago" if n == 1 else f"{n} hours ago"
    if days < 2:
        return "yesterday"
    if days < 30:
        return f"{round(days)} days ago"
    if days < 365:
        n = round(days / 30)
        return "1 month ago" if n == 1 else f"{n} months ago"
    n = round(days / 365)
    return "1 year ago" if n == 1 else f"{n} years ago"


# --- Internal helpers ------------------------------------------------------


def _looks_numeric(cell: str) -> bool:
    """True if ``cell`` is digit-led and made only of number-ish characters."""
    stripped = cell.strip()
    return bool(stripped) and bool(_NUMERIC_CELL.match(stripped))
