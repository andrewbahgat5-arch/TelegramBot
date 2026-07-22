"""Localization (i18n) catalog loader (MASTER_PLAN Sprint 11.5).

Flat, dot-named translation keys loaded from ``core/locales/*.json``. The default
locale (``core/config.py``'s ``Settings.default_locale``, env ``DEFAULT_LOCALE``) is
the reference catalog: every real translation key must exist there, and every other
discovered locale is validated to be a subset of it, so a typo'd key in a
non-default catalog fails at startup instead of silently falling back forever.

Supported languages are discovered from disk, never stored in the database —
adding a language is "drop in one file with ``_meta.enabled: true``", no code or
schema change (Owner directive).

This module has no import-time dependency on ``Settings`` (it would need env vars
that aren't available in every context, e.g. plain unit tests) — call
:func:`configure` once, explicitly, from the composition root (mirrors
``core/logging.py``'s ``configure_logging`` + ``get_logger`` pattern).
"""

from __future__ import annotations

import json
import string
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from core.logging import get_logger

_log = get_logger("core.i18n")

_DEFAULT_LOCALES_DIR: Final[Path] = Path(__file__).parent / "locales"
_META_KEY: Final[str] = "_meta"
_VALID_DIRECTIONS: Final[frozenset[str]] = frozenset({"ltr", "rtl"})

# Coverage carve-out (V2-D-026): admin/owner-only surfaces are intentionally left
# untranslated in most locales, so counting them would drown the *user-facing*
# coverage signal the metric exists to expose. The V2 plan names this the "admin.*
# carve-out"; in this codebase the admin-facing keys live under these namespaces —
# the inline admin panel (``panel.``, Sprint 9.6/14), admin notifications
# (``adminnotify.``), the cookie-pool panel (``cookies.``), and ``admin.`` itself.
_ADMIN_COVERAGE_PREFIXES: Final[tuple[str, ...]] = (
    "admin.",
    "panel.",
    "adminnotify.",
    "cookies.",
)

# Handler/keyboard-layer type alias for the composition-root-injected `translate`
# (`dp["translate"]`, Sprint 11.5) — one shared name instead of repeating the bare
# Callable shape across every file that takes it as a parameter.
Translator = Callable[..., str]


class LocaleCatalogError(Exception):
    """Raised when a locale catalog is malformed or inconsistent (fail fast)."""


@dataclass(frozen=True, slots=True)
class LocaleMeta:
    """Metadata carried by every catalog's reserved ``_meta`` key."""

    code: str
    native_name: str
    direction: str
    enabled: bool
    version: int


@dataclass(frozen=True, slots=True)
class _State:
    catalogs: dict[str, dict[str, str]]
    metas: dict[str, LocaleMeta]
    default_locale: str
    coverage: dict[str, float]


_state: _State | None = None

# Admin-editable message-template overrides (Sprint 13.8): ``(locale, key) -> template``.
# Consulted by :func:`translate` before the on-disk catalog, so a custom template
# transparently overrides the shipped default for the same key. Populated at startup
# (and on every edit) by ``services.template_service.TemplateService`` — a read-heavy,
# write-rare in-memory map, never a per-call DB query.
_overrides: dict[tuple[str, str], str] = {}


def set_template_overrides(overrides: dict[tuple[str, str], str]) -> None:
    """Replace the custom message-template overrides (Sprint 13.8). Idempotent."""
    _overrides.clear()
    _overrides.update(overrides)


def catalog_template(key: str, locale: str) -> str | None:
    """The raw on-disk template for ``key`` (ignoring overrides), or None.

    Used by the templates admin screen to preview the *shipped default* even when a
    custom override is active. Falls back to the default locale like :func:`translate`.
    """
    state = _require_state()
    template = state.catalogs.get(locale, {}).get(key)
    if template is None:
        template = state.catalogs[state.default_locale].get(key)
    return template


def configure(default_locale: str, *, locales_dir: Path | None = None) -> None:
    """Discover, parse, and validate every locale catalog. Call once at startup.

    Idempotent — safe to call again (e.g. once per test) to reconfigure. Clears any
    message-template overrides so a fresh catalog never carries stale custom text.
    """
    directory = locales_dir or _DEFAULT_LOCALES_DIR
    if not directory.is_dir():
        raise LocaleCatalogError(f"locales directory not found: {directory}")

    catalogs: dict[str, dict[str, str]] = {}
    metas: dict[str, LocaleMeta] = {}
    for path in sorted(directory.glob("*.json")):
        raw = _read_json(path)
        _reject_stray_underscore_keys(path, raw)
        meta = _parse_meta(path, raw.get(_META_KEY))
        catalogs[meta.code] = _extract_string_values(path, raw)
        metas[meta.code] = meta

    if default_locale not in catalogs:
        raise LocaleCatalogError(
            f"DEFAULT_LOCALE={default_locale!r} has no matching catalog file in {directory}"
        )
    if not metas[default_locale].enabled:
        raise LocaleCatalogError(
            f"DEFAULT_LOCALE={default_locale!r}'s catalog is marked _meta.enabled=false"
        )
    _reject_orphaned_keys(catalogs, default_locale)
    _reject_alien_placeholders(catalogs, default_locale)

    global _state
    _state = _State(
        catalogs=catalogs,
        metas=metas,
        default_locale=default_locale,
        coverage=_compute_coverage(catalogs, default_locale),
    )
    _overrides.clear()


def translate(key: str, locale: str, **kwargs: object) -> str:
    """Resolve ``key`` in ``locale``, falling back to the default locale, then the
    key itself. Every fallback is logged; a bad ``.format()`` placeholder is caught
    and logged rather than raised (no path here may crash the caller)."""
    state = _require_state()
    template = _overrides.get((locale, key))
    if template is None:
        template = state.catalogs.get(locale, {}).get(key)
    if template is None:
        if locale != state.default_locale:
            _log.warning("i18n_key_fallback_to_default", key=key, locale=locale)
        template = state.catalogs[state.default_locale].get(key)
    if template is None:
        _log.warning("i18n_key_missing", key=key, locale=locale)
        return key
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError) as exc:
        _log.warning("i18n_format_error", key=key, locale=locale, error=str(exc))
        return template


def resolve_locale(stored: str | None) -> str:
    """Effective locale for a user's stored value: itself if enabled, else the
    configured default. Read-only — never mutates the stored value, so a
    since-disabled (or never-set) locale recovers automatically once available."""
    state = _require_state()
    if stored is not None and stored in state.catalogs and state.metas[stored].enabled:
        return stored
    return state.default_locale


def list_enabled_locales() -> list[LocaleMeta]:
    """Every discovered locale with ``_meta.enabled: true``, for the picker keyboard."""
    state = _require_state()
    return [meta for meta in state.metas.values() if meta.enabled]


def catalog_coverage() -> dict[str, float]:
    """Per-locale translation coverage in ``[0.0, 1.0]`` (V2-D-026).

    The fraction of the default locale's **user-facing** keys (admin/owner-only
    namespaces carved out, see :data:`_ADMIN_COVERAGE_PREFIXES`) that the locale
    translates. The default locale is always ``1.0``. Computed once at
    :func:`configure` time; the composition root publishes it to the
    ``i18n_catalog_coverage`` gauge. Returns a fresh copy.
    """
    return dict(_require_state().coverage)


def _require_state() -> _State:
    if _state is None:
        raise RuntimeError("core.i18n.configure() must be called before use")
    return _state


def _read_json(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LocaleCatalogError(f"{path.name}: could not read/parse: {exc}") from exc
    if not isinstance(raw, dict) or _META_KEY not in raw:
        raise LocaleCatalogError(f"{path.name}: missing required {_META_KEY!r} key")
    return raw


def _extract_string_values(path: Path, raw: dict[str, object]) -> dict[str, str]:
    """Every non-``_meta`` catalog entry must be a string template; reject anything
    else (a nested object, a number, …) loudly rather than storing a non-string
    value core.i18n.translate() would later fail to ``.format()``."""
    result: dict[str, str] = {}
    for key, value in raw.items():
        if key == _META_KEY:
            continue
        if not isinstance(value, str):
            raise LocaleCatalogError(
                f"{path.name}: {key!r} must be a string, got {type(value).__name__}"
            )
        result[key] = value
    return result


def _reject_stray_underscore_keys(path: Path, raw: dict[str, object]) -> None:
    stray = [k for k in raw if k.startswith("_") and k != _META_KEY]
    if stray:
        raise LocaleCatalogError(
            f"{path.name}: key(s) {sorted(stray)} start with '_' but only {_META_KEY!r} "
            "is a reserved key — application keys must not start with '_'"
        )


def _parse_meta(path: Path, raw_meta: object) -> LocaleMeta:
    if not isinstance(raw_meta, dict):
        raise LocaleCatalogError(f"{path.name}: {_META_KEY!r} must be an object")
    code = raw_meta.get("code")
    if code != path.stem:
        raise LocaleCatalogError(
            f"{path.name}: _meta.code {code!r} does not match filename {path.stem!r}"
        )
    native_name = raw_meta.get("native_name")
    if not isinstance(native_name, str) or not native_name:
        raise LocaleCatalogError(f"{path.name}: _meta.native_name must be a non-empty string")
    direction = raw_meta.get("direction")
    if direction not in _VALID_DIRECTIONS:
        raise LocaleCatalogError(
            f"{path.name}: _meta.direction must be one of {sorted(_VALID_DIRECTIONS)}, "
            f"got {direction!r}"
        )
    enabled = raw_meta.get("enabled")
    if not isinstance(enabled, bool):
        raise LocaleCatalogError(f"{path.name}: _meta.enabled must be a boolean")
    version = raw_meta.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise LocaleCatalogError(f"{path.name}: _meta.version must be a positive integer")
    return LocaleMeta(
        code=code, native_name=native_name, direction=direction, enabled=enabled, version=version
    )


def _reject_orphaned_keys(catalogs: dict[str, dict[str, str]], default_locale: str) -> None:
    """Every non-default catalog's keys must be a subset of the default's (typo guard)."""
    default_keys = set(catalogs[default_locale])
    for code, catalog in catalogs.items():
        if code == default_locale:
            continue
        orphaned = set(catalog) - default_keys
        if orphaned:
            raise LocaleCatalogError(
                f"locale {code!r} defines key(s) {sorted(orphaned)} absent from the default "
                f"locale {default_locale!r} catalog — likely a typo"
            )


def _placeholder_names(template: str) -> set[str]:
    """The set of ``{name}`` field names referenced by a ``.format()`` template.

    Format spec, conversion, attribute (``{a.b}``) and index (``{a[0]}``) syntax are
    stripped to the top-level field name; literal text and auto-numbered ``{}`` fields
    contribute nothing. ``{{``/``}}`` escapes are handled by :class:`string.Formatter`.
    """
    names: set[str] = set()
    for _literal, field_name, _spec, _conv in string.Formatter().parse(template):
        if field_name:  # None => literal chunk; "" => auto-positional; both irrelevant
            names.add(field_name.split(".", 1)[0].split("[", 1)[0])
    return names


def _reject_alien_placeholders(catalogs: dict[str, dict[str, str]], default_locale: str) -> None:
    """Every non-default template's placeholders must be a subset of the default's.

    Callers pass the kwargs the *default* template declares; a translation that
    references a placeholder the default does not have would raise ``KeyError`` inside
    :func:`translate` and degrade to a raw, brace-riddled template shown to the user
    (the exact defect V2-D-026 makes statically checkable). Orphaned keys are already
    rejected, so every key here also exists in the default catalog. A translation may
    *omit* placeholders (subset), it may never *invent* them.
    """
    default = catalogs[default_locale]
    for code, catalog in catalogs.items():
        if code == default_locale:
            continue
        for key, template in catalog.items():
            expected = _placeholder_names(default.get(key, ""))
            alien = _placeholder_names(template) - expected
            if alien:
                raise LocaleCatalogError(
                    f"locale {code!r} key {key!r} references placeholder(s) {sorted(alien)} "
                    f"absent from the default locale {default_locale!r} template "
                    f"(expected a subset of {sorted(expected)}) — would surface to users as a "
                    "raw template"
                )


def _compute_coverage(catalogs: dict[str, dict[str, str]], default_locale: str) -> dict[str, float]:
    """Fraction of default user-facing keys each locale translates (V2-D-026).

    Admin/owner-only namespaces are excluded (:data:`_ADMIN_COVERAGE_PREFIXES`) so the
    metric tracks the user-facing surface. The default locale is ``1.0`` by definition.
    """
    default_keys = [
        k for k in catalogs[default_locale] if not k.startswith(_ADMIN_COVERAGE_PREFIXES)
    ]
    total = len(default_keys)
    if total == 0:
        return {code: 1.0 for code in catalogs}
    return {
        code: sum(1 for k in default_keys if k in catalog) / total
        for code, catalog in catalogs.items()
    }
