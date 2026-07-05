"""Panel action registry (Sprint 9.6, F-2 / EP-22; Sprint 11.5 i18n).

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

Every ``label`` field below is a ``core.i18n`` translation key (a dot-named
string looked up at render time), not literal display text — the keyboard layer
(``bot/keyboards/admin_panel.py``) resolves it via ``translate(key, locale)``.
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
    label_key: str  # core.i18n key for the main-menu button text
    owner_only: bool = False  # hidden from moderators (no read-only view)


SECTIONS: tuple[Section, ...] = (
    Section("u", "panel.section.users"),
    Section("a", "panel.section.advertisements"),
    Section("r", "panel.section.referrals"),  # Sprint 13.7
    Section("b", "panel.section.broadcast", owner_only=True),
    Section("s", "panel.section.settings"),
    Section("t", "panel.section.statistics"),
    Section("h", "panel.section.history"),
    Section("m", "panel.section.moderation"),
    Section("d", "panel.section.downloads"),
    Section("y", "panel.section.system"),
    Section("tp", "panel.section.templates", owner_only=True),  # Sprint 13.8
    # Personal language preference (Sprint 11.5) — not an administrative mutation
    # (zero blast radius, affects only the acting staff member's own row), so it's
    # visible to both roles like any other read-tier section.
    Section("l", "panel.section.language"),
)


# --- Submenu registry -----------------------------------------------------
# Static action menus per section. Write-tier items are hidden from moderators
# (rendered role-aware in the keyboard layer); Settings (``s``) is generated from
# SETTING_FIELDS instead of a static list.


@dataclass(frozen=True, slots=True)
class MenuItem:
    """One submenu button. Its authorization tier derives from ``action``."""

    label_key: str
    action: str
    arg: int | None = None


SUBMENUS: dict[str, tuple[MenuItem, ...]] = {
    "u": (
        MenuItem("panel.action.list", "ls"),
        MenuItem("panel.menu.u.userinfo", "inf"),
        MenuItem("panel.action.ban", "ban"),
        MenuItem("panel.action.unban", "ubn"),
        MenuItem("panel.menu.u.upgrade_premium", "up"),
        MenuItem("panel.menu.u.remove_premium", "rp"),
        MenuItem("panel.menu.u.make_admin", "mka"),
        MenuItem("panel.menu.u.remove_admin", "rma"),
        # Subscriber export/import (Sprint 13.6) — owner-only (write-tier actions).
        MenuItem("panel.menu.u.export", "exp"),
        MenuItem("panel.menu.u.import", "imp"),
    ),
    "a": (
        MenuItem("panel.action.list", "ls"),
        MenuItem("panel.action.create", "cr"),
        MenuItem("panel.action.edit", "ed"),
        MenuItem("panel.action.enable", "en"),
        MenuItem("panel.action.disable", "di"),
        MenuItem("panel.action.delete", "de"),
        MenuItem("panel.action.broadcast", "bc"),
        MenuItem("panel.menu.a.stats", "stt"),
    ),
    "b": (
        MenuItem("panel.action.create", "cr"),
        MenuItem("panel.menu.b.free", "bf"),
        MenuItem("panel.menu.b.premium", "bp"),
        MenuItem("panel.menu.b.all", "ba"),
        MenuItem("panel.menu.b.by_language", "bl"),
    ),
    "t": (
        MenuItem("panel.menu.t.refresh", "ls"),
        # Platform analytics sub-screen (Sprint 13.3); arg=3 opens the all-time view.
        MenuItem("panel.menu.t.platforms", "stt", arg=3),
    ),
    "r": (MenuItem("panel.menu.r.refresh", "ls"),),  # Sprint 13.7 referral dashboard
    "h": (MenuItem("panel.action.list", "ls"),),
    "m": (
        MenuItem("panel.menu.m.banned_list", "ls"),
        MenuItem("panel.action.ban", "ban"),
        MenuItem("panel.action.unban", "ubn"),
    ),
    "d": (
        MenuItem("panel.menu.d.queue_status", "inf"),
        MenuItem("panel.menu.d.active_jobs", "ls"),
    ),
    "y": (
        MenuItem("panel.menu.y.status", "inf"),
        MenuItem("panel.menu.y.errors", "ls"),
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
    label_key: str
    step: int
    min_value: int
    max_value: int


SETTING_FIELDS: tuple[SettingField, ...] = (
    SettingField(0, "worker_count", "panel.settings.field.worker_count", 1, 1, 32),
    SettingField(1, "free_daily_limit", "panel.settings.field.free_daily_limit", 5, 0, 100_000),
    SettingField(
        2, "premium_daily_limit", "panel.settings.field.premium_daily_limit", 10, 0, 1_000_000
    ),
    SettingField(
        3,
        "download_cooldown_seconds",
        "panel.settings.field.download_cooldown_seconds",
        5,
        0,
        3_600,
    ),
    SettingField(
        4,
        "premium_download_cooldown_seconds",
        "panel.settings.field.premium_download_cooldown_seconds",
        1,
        0,
        3_600,
    ),
    SettingField(5, "max_duration", "panel.settings.field.max_duration", 600, 60, 86_400),
    SettingField(
        6,
        "rate_limit_messages_per_minute",
        "panel.settings.field.rate_limit_messages_per_minute",
        5,
        1,
        600,
    ),
    SettingField(7, "history_page_size", "panel.settings.field.history_page_size", 1, 1, 50),
    SettingField(8, "broadcast_chunk_size", "panel.settings.field.broadcast_chunk_size", 5, 1, 100),
    SettingField(
        9, "ads_default_frequency", "panel.settings.field.ads_default_frequency", 1, 1, 100
    ),
    SettingField(
        10,
        "error_log_retention_days",
        "panel.settings.field.error_log_retention_days",
        30,
        1,
        3_650,
    ),
    SettingField(
        11,
        "downloads_retention_days",
        "panel.settings.field.downloads_retention_days",
        30,
        1,
        3_650,
    ),
    SettingField(
        12, "jobs_retention_days", "panel.settings.field.jobs_retention_days", 30, 1, 3_650
    ),
    SettingField(
        13,
        "provider_cooldown_seconds",
        "panel.settings.field.provider_cooldown_seconds",
        30,
        0,
        3_600,
    ),
    SettingField(
        14,
        "provider_health_check_interval_seconds",
        "panel.settings.field.provider_health_check_interval_seconds",
        30,
        10,
        3_600,
    ),
    SettingField(
        15,
        "provider_failure_threshold",
        "panel.settings.field.provider_failure_threshold",
        1,
        1,
        100,
    ),
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
    label_key: str


SETTINGS_INFO: tuple[InfoItem, ...] = (
    InfoItem(0, "panel.settings.info.cache"),
    InfoItem(1, "panel.settings.info.languages"),
)


# --- Compose-wizard registries (Sprint 9.6, D-059) ------------------------
# The audience builder and placement builder render *from these registries*, so a new
# dimension or placement is a registration here, not a change to the wizard engine.
# ``index`` is the compact callback ``arg`` (keeps signed callback_data tiny, §14.2).


@dataclass(frozen=True, slots=True)
class AudienceOption:
    """One toggle in the audience builder. ``value=None`` ⇒ a typed sub-input."""

    index: int
    label_key: str
    effect: str  # include | exclude
    dimension: str  # plan | role | language | user_id | segment
    value: str | None  # concrete value, or None for a typed sub-input (language/user id)


AUDIENCE_OPTIONS: tuple[AudienceOption, ...] = (
    AudienceOption(0, "panel.audience.free", "include", "plan", "free"),
    AudienceOption(1, "panel.audience.premium", "include", "plan", "premium"),
    AudienceOption(2, "panel.audience.users_role", "include", "role", "user"),
    AudienceOption(3, "panel.audience.language", "include", "language", None),
    AudienceOption(4, "panel.audience.user_id", "include", "user_id", None),
    AudienceOption(5, "panel.audience.exclude_premium", "exclude", "plan", "premium"),
    AudienceOption(6, "panel.audience.exclude_free", "exclude", "plan", "free"),
    AudienceOption(7, "panel.audience.exclude_owner", "exclude", "role", "owner"),
    AudienceOption(8, "panel.audience.exclude_moderators", "exclude", "role", "moderator"),
    AudienceOption(9, "panel.audience.exclude_user_id", "exclude", "user_id", None),
)


def audience_option(index: int | None) -> AudienceOption | None:
    if index is not None and 0 <= index < len(AUDIENCE_OPTIONS):
        return AUDIENCE_OPTIONS[index]
    return None


@dataclass(frozen=True, slots=True)
class PlacementOption:
    index: int
    code: str  # an AdPlacement value (D-044)
    label_key: str


PLACEMENT_OPTIONS: tuple[PlacementOption, ...] = (
    PlacementOption(0, "post_download", "panel.placement.post_download"),
    PlacementOption(1, "video_delivery", "panel.placement.video_delivery"),
    PlacementOption(2, "audio_delivery", "panel.placement.audio_delivery"),
    PlacementOption(3, "quality_select", "panel.placement.quality_select"),
    PlacementOption(4, "home", "panel.placement.home"),
    PlacementOption(5, "history", "panel.placement.history"),
)


def placement_option(index: int | None) -> PlacementOption | None:
    if index is not None and 0 <= index < len(PLACEMENT_OPTIONS):
        return PLACEMENT_OPTIONS[index]
    return None
