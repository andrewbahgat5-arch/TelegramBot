"""Panel action registry (Sprint 9.6, F-2 / EP-22).

The single source of truth for panel action codes and their authorization tier,
so the :class:`~bot.filters.panel_filter.PanelFilter` and the keyboard builders
agree and new sections / future plugins extend exactly one place.

Tier rule (security-first): an action is **READ** (staff-visible: owner *and*
moderator) only if it is explicitly listed here; *everything else* — every
mutation, every destructive-confirm screen, every wizard step — defaults to
**WRITE** (owner-only). Forgetting to list a new action therefore fails safe
(denied to moderators), never the reverse. This pairs with hiding write buttons
from moderators in the keyboard layer (defense in depth, MASTER_PLAN §9.1 — authz
never decided in handler bodies).

Action codes are short, opaque tokens carried in the signed ``P`` callback
(``bot/callbacks/factory.py``). Read/navigation codes only *open menus, page
lists, and view details* — never an affordance that mutates without a further
owner-gated press (so an "open delete-confirm" screen is WRITE, not READ).
"""

from __future__ import annotations

from dataclasses import dataclass

# Read / navigation actions. Non-mutating and lead to no mutation on their own.
READ_ACTIONS: frozenset[str] = frozenset(
    {
        "op",  # open a section menu / submenu
        "bk",  # back to the parent menu
        "hm",  # home — the root admin panel
        "pg",  # paginate a list
        "ls",  # (re-)render a list
        "inf",  # view an entity detail (user info, queue/system status, …)
        "stt",  # view statistics (ad stats, totals)
        "cx",  # cancel / abort a wizard (non-mutating; returns to a menu)
    }
)


def is_write_action(action: str) -> bool:
    """True if ``action`` mutates state or leads to one (owner-only tier).

    Unknown codes are treated as WRITE so an unregistered action fails safe.
    """
    return action not in READ_ACTIONS


# --- Section registry -----------------------------------------------------
# The main menu is *generated* from this tuple (no hardcoded buttons), so a new
# section — or a future plugin module (Analytics, Payments, AI, Sponsors, …) —
# is added by appending one entry, with no change to navigation logic.


@dataclass(frozen=True, slots=True)
class Section:
    """A top-level panel section. ``code`` is the ``P`` callback section token."""

    code: str
    label: str  # emoji + text shown on the main-menu button
    owner_only: bool = False  # hidden from moderators (no read-only view)


SECTIONS: tuple[Section, ...] = (
    Section("u", "👥 Users"),
    Section("a", "📢 Advertisements"),
    Section("b", "📣 Broadcast", owner_only=True),
    Section("s", "⚙️ Settings"),
    Section("t", "📊 Statistics"),
    Section("h", "📂 History"),
    Section("m", "🚫 Moderation"),
    Section("d", "📥 Downloads"),
    Section("y", "🔧 System"),
)


# --- Submenu registry -----------------------------------------------------
# Static action menus per section. Write-tier items are hidden from moderators
# (rendered role-aware in the keyboard layer); Settings (``s``) is generated from
# SETTING_FIELDS instead of a static list.


@dataclass(frozen=True, slots=True)
class MenuItem:
    """One submenu button. Its authorization tier derives from ``action``."""

    label: str
    action: str
    arg: int | None = None


SUBMENUS: dict[str, tuple[MenuItem, ...]] = {
    "u": (
        MenuItem("📋 List", "ls"),
        MenuItem("🔍 User Info", "inf"),
        MenuItem("🚫 Ban", "ban"),
        MenuItem("✅ Unban", "ubn"),
        MenuItem("⭐ Upgrade Premium", "up"),
        MenuItem("⬇️ Remove Premium", "rp"),
        MenuItem("🛡 Make Admin", "mka"),
        MenuItem("👤 Remove Admin", "rma"),
    ),
    "a": (
        MenuItem("📋 List", "ls"),
        MenuItem("🆕 Create", "cr"),
        MenuItem("✏️ Edit", "ed"),
        MenuItem("✅ Enable", "en"),
        MenuItem("⏸ Disable", "di"),
        MenuItem("🗑 Delete", "de"),
        MenuItem("📢 Broadcast", "bc"),
        MenuItem("📊 Statistics", "stt"),
    ),
    "b": (
        MenuItem("🆕 Create", "cr"),
        MenuItem("🆓 Free Users", "bf"),
        MenuItem("⭐ Premium Users", "bp"),
        MenuItem("👥 All Users", "ba"),
        MenuItem("🌐 By Language", "bl"),
    ),
    "t": (MenuItem("🔄 Refresh", "ls"),),
    "h": (MenuItem("📋 List", "ls"),),
    "m": (
        MenuItem("📋 Banned Users", "ls"),
        MenuItem("🚫 Ban", "ban"),
        MenuItem("✅ Unban", "ubn"),
    ),
    "d": (
        MenuItem("📊 Queue Status", "inf"),
        MenuItem("⏳ Active Jobs", "ls"),
    ),
    "y": (
        MenuItem("🔧 Status", "inf"),
        MenuItem("⚠️ Errors", "ls"),
    ),
}


# --- Setting-field registry (stepper) -------------------------------------
# Only LOCKED §13.4 int keys that are sensible to edit with a ±step stepper.
# ``index`` is the compact callback ``arg`` (keeps callback_data tiny — raw keys
# like ``provider_health_check_interval_seconds`` would blow the 64-byte limit).
# ``min_value``/``max_value`` are UI guard rails only; the authoritative check
# stays ``SettingsService.set_validated`` on Save. Byte-valued size keys and
# bool/json keys are deliberately excluded (handled as typed input / toggles).


@dataclass(frozen=True, slots=True)
class SettingField:
    index: int
    key: str  # an EXISTING LOCKED settings key (§13.4) — never invented
    label: str
    step: int
    min_value: int
    max_value: int


SETTING_FIELDS: tuple[SettingField, ...] = (
    SettingField(0, "worker_count", "Workers", 1, 1, 32),
    SettingField(1, "free_daily_limit", "Free Daily Limit", 5, 0, 100_000),
    SettingField(2, "premium_daily_limit", "Premium Daily Limit", 10, 0, 1_000_000),
    SettingField(3, "download_cooldown_seconds", "Free Cooldown (s)", 5, 0, 3_600),
    SettingField(4, "premium_download_cooldown_seconds", "Premium Cooldown (s)", 1, 0, 3_600),
    SettingField(5, "max_duration", "Max Duration (s)", 600, 60, 86_400),
    SettingField(6, "rate_limit_messages_per_minute", "Msg Rate / min", 5, 1, 600),
    SettingField(7, "history_page_size", "History Page Size", 1, 1, 50),
    SettingField(8, "broadcast_chunk_size", "Broadcast Chunk Size", 5, 1, 100),
    SettingField(9, "ads_default_frequency", "Ads Frequency", 1, 1, 100),
    SettingField(10, "error_log_retention_days", "Error Log Retention (d)", 30, 1, 3_650),
    SettingField(11, "downloads_retention_days", "Downloads Retention (d)", 30, 1, 3_650),
    SettingField(12, "jobs_retention_days", "Jobs Retention (d)", 30, 1, 3_650),
    SettingField(13, "provider_cooldown_seconds", "Provider Cooldown (s)", 30, 0, 3_600),
    SettingField(
        14, "provider_health_check_interval_seconds", "Provider Health Interval (s)", 30, 10, 3_600
    ),
    SettingField(15, "provider_failure_threshold", "Provider Failure Threshold", 1, 1, 100),
)


def setting_field(index: int) -> SettingField | None:
    """Look up a stepper field by its compact callback index; None if out of range."""
    if 0 <= index < len(SETTING_FIELDS):
        return SETTING_FIELDS[index]
    return None


# --- Settings info screens ------------------------------------------------
# Read-only screens for Owner-spec submenu items that have no LOCKED settings key
# (so we never invent one). Rendered by the read handler, viewable by all staff.


@dataclass(frozen=True, slots=True)
class InfoItem:
    index: int
    label: str


SETTINGS_INFO: tuple[InfoItem, ...] = (
    InfoItem(0, "🗃 Cache"),
    InfoItem(1, "🌐 Languages"),
)


# --- Compose-wizard registries (Sprint 9.6, D-059) ------------------------
# The audience builder and placement builder render *from these registries*, so a new
# dimension or placement is a registration here, not a change to the wizard engine.
# ``index`` is the compact callback ``arg`` (keeps signed callback_data tiny, §14.2).


@dataclass(frozen=True, slots=True)
class AudienceOption:
    """One toggle in the audience builder. ``value=None`` ⇒ a typed sub-input."""

    index: int
    label: str
    effect: str  # include | exclude
    dimension: str  # plan | role | language | user_id | segment
    value: str | None  # concrete value, or None for a typed sub-input (language/user id)


AUDIENCE_OPTIONS: tuple[AudienceOption, ...] = (
    AudienceOption(0, "🆓 Free", "include", "plan", "free"),
    AudienceOption(1, "⭐ Premium", "include", "plan", "premium"),
    AudienceOption(2, "👤 Users", "include", "role", "user"),
    AudienceOption(3, "🌐 Language…", "include", "language", None),
    AudienceOption(4, "🆔 User ID…", "include", "user_id", None),
    AudienceOption(5, "🚫 Premium", "exclude", "plan", "premium"),
    AudienceOption(6, "🚫 Free", "exclude", "plan", "free"),
    AudienceOption(7, "🚫 Owner", "exclude", "role", "owner"),
    AudienceOption(8, "🚫 Moderators", "exclude", "role", "moderator"),
    AudienceOption(9, "🚫 User ID…", "exclude", "user_id", None),
)


def audience_option(index: int | None) -> AudienceOption | None:
    if index is not None and 0 <= index < len(AUDIENCE_OPTIONS):
        return AUDIENCE_OPTIONS[index]
    return None


@dataclass(frozen=True, slots=True)
class PlacementOption:
    index: int
    code: str  # an AdPlacement value (D-044)
    label: str


PLACEMENT_OPTIONS: tuple[PlacementOption, ...] = (
    PlacementOption(0, "post_download", "📥 Post-download"),
    PlacementOption(1, "video_delivery", "🎬 Video"),
    PlacementOption(2, "audio_delivery", "🎵 Audio"),
    PlacementOption(3, "quality_select", "🎚 Quality"),
    PlacementOption(4, "home", "🏠 Home"),
    PlacementOption(5, "history", "📂 History"),
)


def placement_option(index: int | None) -> PlacementOption | None:
    if index is not None and 0 <= index < len(PLACEMENT_OPTIONS):
        return PLACEMENT_OPTIONS[index]
    return None
