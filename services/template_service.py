"""TemplateService (Sprint 13.8) — admin-editable user-facing messages.

Owns the small set of user-facing messages an admin may override from the panel
(``TEMPLATE_DEFS``). Custom text is stored per ``(key, locale)`` and mirrored into an
in-memory cache plus ``core.i18n``'s override map, so the message layer keeps calling
``translate(i18n_key, locale)`` unchanged and transparently gets the custom copy.

Read-heavy, write-rare: the cache is loaded once at startup (:meth:`load`) and only
re-synced on an edit — never a per-message DB query (SPRINT_13_PLAN §13.8).
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from core import i18n
from core.logging import get_logger

_log = get_logger("services.template_service")

_PREVIEW_LEN = 80


@dataclass(frozen=True, slots=True)
class TemplateDef:
    """One editable template: its short ``key``, the i18n key it overrides, its params."""

    key: str
    i18n_key: str
    placeholders: tuple[str, ...]
    placeholder_help: tuple[tuple[str, str], ...] = ()
    allow_buttons: bool = False


TEMPLATE_DEFS: tuple[TemplateDef, ...] = (
    TemplateDef(
        "welcome", "user.welcome", ("name",),
        placeholder_help=(("name", "Andrew"),),
    ),
    TemplateDef("help", "user.help", ()),
    TemplateDef(
        "download_started", "download.started", ("title", "platform"),
        placeholder_help=(("title", "My Video"), ("platform", "YouTube")),
    ),
    TemplateDef(
        "download_failed", "download.failed", ("error",),
        placeholder_help=(("error", "File too large"),),
    ),
    TemplateDef(
        "daily_limit_reached", "limit.daily_reached", ("limit", "reset_in"),
        placeholder_help=(("limit", "10"), ("reset_in", "6h")),
    ),
    TemplateDef(
        "banned_message", "user.banned", ("reason",),
        placeholder_help=(("reason", "Spam"),),
        allow_buttons=True,
    ),
    TemplateDef(
        "cooldown_message", "limit.cooldown", ("seconds",),
        placeholder_help=(("seconds", "30"),),
    ),
    TemplateDef("maintenance", "system.maintenance", (), allow_buttons=True),
)

_DEF_BY_KEY: dict[str, TemplateDef] = {d.key: d for d in TEMPLATE_DEFS}


class MessageTemplateStore(Protocol):
    """The persistence surface TemplateService depends on (rows expose the columns)."""

    async def load_all(self) -> Sequence[Any]: ...
    async def get(self, key: str, locale: str) -> Any | None: ...
    async def upsert(
        self, key: str, locale: str, content: str, *, updated_by: int | None = None
    ) -> None: ...
    async def set_buttons(
        self, key: str, locale: str, buttons: list[dict[str, str]] | None
    ) -> None: ...
    async def delete_template(self, key: str, locale: str) -> None: ...


@dataclass(frozen=True, slots=True)
class TemplateView:
    """A template's admin-display state: custom-vs-default and a short preview."""

    key: str
    locale: str
    is_custom: bool
    content_preview: str
    updated_at: datetime.datetime | None


class TemplateService:
    def __init__(self, store: MessageTemplateStore) -> None:
        self._store = store
        self._cache: dict[tuple[str, str], tuple[str, datetime.datetime | None]] = {}
        self._buttons_cache: dict[tuple[str, str], list[dict[str, str]]] = {}

    async def load(self) -> None:
        """Warm the cache from the store and push overrides into core.i18n (startup)."""
        rows = await self._store.load_all()
        self._cache = {
            (row.key, row.locale): (row.content, getattr(row, "updated_at", None))
            for row in rows
            if row.key in _DEF_BY_KEY
        }
        self._buttons_cache = {
            (row.key, row.locale): row.buttons
            for row in rows
            if row.key in _DEF_BY_KEY and getattr(row, "buttons", None)
        }
        self._sync_overrides()

    async def get(self, key: str, locale: str) -> str | None:
        """Custom content for a template, or None (caller falls back to i18n default)."""
        entry = self._cache.get((key, locale))
        return None if entry is None else entry[0]

    async def set(self, key: str, locale: str, content: str, updated_by: int) -> None:
        """Upsert a custom template, then re-sync the cache and i18n overrides."""
        if key not in _DEF_BY_KEY:
            raise KeyError(f"unknown template key: {key}")
        await self._store.upsert(key, locale, content, updated_by=updated_by)
        self._cache[(key, locale)] = (content, datetime.datetime.now(datetime.UTC))
        self._sync_overrides()
        _log.info("template_set", key=key, locale=locale, updated_by=updated_by)

    async def reset(self, key: str, locale: str) -> None:
        """Delete a custom template, reverting to the i18n default; re-sync overrides."""
        await self._store.delete_template(key, locale)
        self._cache.pop((key, locale), None)
        self._sync_overrides()
        _log.info("template_reset", key=key, locale=locale)

    async def list_all(self, locale: str) -> list[TemplateView]:
        """Every editable template with its custom/default status and a preview."""
        views: list[TemplateView] = []
        for definition in TEMPLATE_DEFS:
            entry = self._cache.get((definition.key, locale))
            if entry is not None:
                content, updated_at = entry
                views.append(
                    TemplateView(
                        key=definition.key,
                        locale=locale,
                        is_custom=True,
                        content_preview=content[:_PREVIEW_LEN],
                        updated_at=updated_at,
                    )
                )
            else:
                default = i18n.catalog_template(definition.i18n_key, locale) or ""
                views.append(
                    TemplateView(
                        key=definition.key,
                        locale=locale,
                        is_custom=False,
                        content_preview=default[:_PREVIEW_LEN],
                        updated_at=None,
                    )
                )
        return views

    async def invalidate_cache(self) -> None:
        """Reload the cache from the store (e.g. after an out-of-band write)."""
        await self.load()

    def definition(self, key: str) -> TemplateDef | None:
        """The registry entry for an editable template key, or None."""
        return _DEF_BY_KEY.get(key)

    def full_content(self, key: str, locale: str) -> str:
        """Exact stored custom content, or the shipped i18n default (never truncated)."""
        entry = self._cache.get((key, locale))
        if entry is not None:
            return entry[0]
        definition = _DEF_BY_KEY.get(key)
        if definition is None:
            return ""
        return i18n.catalog_template(definition.i18n_key, locale) or ""

    def buttons_for(self, key: str, locale: str) -> list[dict[str, str]]:
        """Cached buttons for a template (list of ``{"text":…,"url":…}``); empty if none."""
        return list(self._buttons_cache.get((key, locale)) or [])

    async def set_buttons(
        self, key: str, locale: str, buttons: list[dict[str, str]] | None
    ) -> None:
        if key not in _DEF_BY_KEY:
            raise KeyError(f"unknown template key: {key}")
        await self._store.set_buttons(key, locale, buttons)
        if buttons:
            self._buttons_cache[(key, locale)] = buttons
        else:
            self._buttons_cache.pop((key, locale), None)
        _log.info("template_buttons_set", key=key, locale=locale, count=len(buttons or []))

    @staticmethod
    def validate_placeholders(content: str, definition: TemplateDef) -> list[str]:
        """Return unknown placeholder names found in ``content``."""
        import re

        found = set(re.findall(r"\{(\w+)\}", content))
        return sorted(found - set(definition.placeholders))

    def _sync_overrides(self) -> None:
        """Rebuild core.i18n's override map from the current cache (keyed by i18n key)."""
        overrides: dict[tuple[str, str], str] = {}
        for (key, locale), (content, _updated) in self._cache.items():
            definition = _DEF_BY_KEY.get(key)
            if definition is not None:
                overrides[(locale, definition.i18n_key)] = content
        i18n.set_template_overrides(overrides)
