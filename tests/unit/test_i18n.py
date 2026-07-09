"""Unit tests for the core i18n catalog loader (Sprint 11.5).

Two kinds of coverage:
* Structural/validation behavior against **crafted temp catalogs** (``tmp_path``) —
  malformed ``_meta``, orphaned keys, reserved-prefix violations, etc.
* Invariants asserted against the **real** ``core/locales/*.json`` catalogs shipped
  with the bot — parity between en/ar, and the ``key``/``locale`` placeholder-name
  collision this module's own ``translate()`` signature can trigger (a real bug found
  and fixed during Sprint 11.5; this guards against it recurring as keys are added).
"""

from __future__ import annotations

import json
import string
from pathlib import Path
from typing import cast

import pytest

import core.i18n as i18n

_REAL_LOCALES_DIR = Path(__file__).resolve().parents[2] / "core" / "locales"


def _write_catalog(directory: Path, code: str, data: dict[str, object]) -> None:
    (directory / f"{code}.json").write_text(json.dumps(data), encoding="utf-8")


def _meta(
    code: str = "en",
    *,
    native_name: str = "English",
    direction: str = "ltr",
    enabled: bool = True,
    version: int = 1,
) -> dict[str, object]:
    return {
        "code": code,
        "native_name": native_name,
        "direction": direction,
        "enabled": enabled,
        "version": version,
    }


# --- discovery + structural validation (crafted temp catalogs) -------------
def test_configure_discovers_enabled_locales(tmp_path: Path) -> None:
    _write_catalog(tmp_path, "en", {"_meta": _meta("en"), "a": "A"})
    _write_catalog(
        tmp_path, "ar", {"_meta": _meta("ar", native_name="العربية", direction="rtl"), "a": "أ"}
    )
    i18n.configure("en", locales_dir=tmp_path)
    codes = {m.code for m in i18n.list_enabled_locales()}
    assert codes == {"en", "ar"}


def test_configure_excludes_disabled_locales(tmp_path: Path) -> None:
    _write_catalog(tmp_path, "en", {"_meta": _meta("en"), "a": "A"})
    _write_catalog(tmp_path, "fr", {"_meta": _meta("fr", native_name="Français", enabled=False)})
    i18n.configure("en", locales_dir=tmp_path)
    codes = {m.code for m in i18n.list_enabled_locales()}
    assert codes == {"en"}  # fr is discovered but not "supported" (enabled=false)


def test_configure_rejects_missing_meta(tmp_path: Path) -> None:
    _write_catalog(tmp_path, "en", {"a": "A"})  # no _meta at all
    with pytest.raises(i18n.LocaleCatalogError, match="_meta"):
        i18n.configure("en", locales_dir=tmp_path)


def test_configure_rejects_code_filename_mismatch(tmp_path: Path) -> None:
    _write_catalog(tmp_path, "en", {"_meta": _meta("something_else")})
    with pytest.raises(i18n.LocaleCatalogError, match="does not match filename"):
        i18n.configure("en", locales_dir=tmp_path)


def test_configure_rejects_invalid_direction(tmp_path: Path) -> None:
    _write_catalog(tmp_path, "en", {"_meta": _meta("en", direction="sideways")})
    with pytest.raises(i18n.LocaleCatalogError, match="direction"):
        i18n.configure("en", locales_dir=tmp_path)


def test_configure_rejects_non_boolean_enabled(tmp_path: Path) -> None:
    meta = _meta("en")
    meta["enabled"] = "yes"  # not a real bool
    _write_catalog(tmp_path, "en", {"_meta": meta})
    with pytest.raises(i18n.LocaleCatalogError, match="enabled"):
        i18n.configure("en", locales_dir=tmp_path)


def test_configure_rejects_non_positive_version(tmp_path: Path) -> None:
    _write_catalog(tmp_path, "en", {"_meta": _meta("en", version=0)})
    with pytest.raises(i18n.LocaleCatalogError, match="version"):
        i18n.configure("en", locales_dir=tmp_path)


def test_configure_rejects_stray_underscore_key(tmp_path: Path) -> None:
    _write_catalog(tmp_path, "en", {"_meta": _meta("en"), "_secret": "oops"})
    with pytest.raises(i18n.LocaleCatalogError, match="reserved"):
        i18n.configure("en", locales_dir=tmp_path)


def test_configure_rejects_orphaned_key_in_non_default_locale(tmp_path: Path) -> None:
    _write_catalog(tmp_path, "en", {"_meta": _meta("en"), "a": "A"})
    _write_catalog(
        tmp_path, "ar", {"_meta": _meta("ar", direction="rtl"), "a": "أ", "typo_key": "x"}
    )
    with pytest.raises(i18n.LocaleCatalogError, match="typo_key"):
        i18n.configure("en", locales_dir=tmp_path)


def test_configure_allows_non_default_locale_missing_keys(tmp_path: Path) -> None:
    """A non-default locale may be a strict subset of the default's keys."""
    _write_catalog(tmp_path, "en", {"_meta": _meta("en"), "a": "A", "b": "B"})
    _write_catalog(tmp_path, "ar", {"_meta": _meta("ar", direction="rtl"), "a": "أ"})
    i18n.configure("en", locales_dir=tmp_path)  # must not raise
    assert i18n.translate("b", "ar") == "B"  # falls back to default


def test_configure_rejects_missing_default_locale(tmp_path: Path) -> None:
    _write_catalog(tmp_path, "en", {"_meta": _meta("en")})
    with pytest.raises(i18n.LocaleCatalogError, match="DEFAULT_LOCALE"):
        i18n.configure("fr", locales_dir=tmp_path)


def test_configure_rejects_disabled_default_locale(tmp_path: Path) -> None:
    _write_catalog(tmp_path, "en", {"_meta": _meta("en", enabled=False)})
    with pytest.raises(i18n.LocaleCatalogError, match="enabled=false"):
        i18n.configure("en", locales_dir=tmp_path)


# --- translate() / resolve_locale() behavior --------------------------------
def test_translate_formats_placeholders(tmp_path: Path) -> None:
    _write_catalog(tmp_path, "en", {"_meta": _meta("en"), "greet": "Hello, {name}!"})
    i18n.configure("en", locales_dir=tmp_path)
    assert i18n.translate("greet", "en", name="Trinity") == "Hello, Trinity!"


def test_translate_falls_back_to_key_when_missing_everywhere(tmp_path: Path) -> None:
    _write_catalog(tmp_path, "en", {"_meta": _meta("en"), "a": "A"})
    i18n.configure("en", locales_dir=tmp_path)
    assert i18n.translate("does.not.exist", "en") == "does.not.exist"


def test_translate_recovers_from_bad_placeholder_without_raising(tmp_path: Path) -> None:
    _write_catalog(tmp_path, "en", {"_meta": _meta("en"), "greet": "Hello, {name}!"})
    i18n.configure("en", locales_dir=tmp_path)
    # Caller forgot to pass `name` — must degrade to the raw template, never raise.
    assert i18n.translate("greet", "en") == "Hello, {name}!"


def test_resolve_locale_passes_through_enabled_code(tmp_path: Path) -> None:
    _write_catalog(tmp_path, "en", {"_meta": _meta("en")})
    _write_catalog(tmp_path, "ar", {"_meta": _meta("ar", direction="rtl")})
    i18n.configure("en", locales_dir=tmp_path)
    assert i18n.resolve_locale("ar") == "ar"


def test_resolve_locale_falls_back_for_unsupported_or_none(tmp_path: Path) -> None:
    _write_catalog(tmp_path, "en", {"_meta": _meta("en")})
    i18n.configure("en", locales_dir=tmp_path)
    assert i18n.resolve_locale("fr") == "en"  # never discovered
    assert i18n.resolve_locale(None) == "en"


def test_resolve_locale_is_read_only_and_recovers_when_reenabled(tmp_path: Path) -> None:
    """A stored code pointing at a currently-disabled locale falls back today, but
    the moment that locale is re-enabled (a fresh `configure()`, e.g. redeploy), the
    exact same stored value resolves again — nothing was written back in between."""
    _write_catalog(tmp_path, "en", {"_meta": _meta("en")})
    _write_catalog(tmp_path, "fr", {"_meta": _meta("fr", native_name="Français", enabled=False)})
    i18n.configure("en", locales_dir=tmp_path)
    assert i18n.resolve_locale("fr") == "en"  # disabled -> falls back, stored value untouched

    _write_catalog(tmp_path, "fr", {"_meta": _meta("fr", native_name="Français", enabled=True)})
    i18n.configure("en", locales_dir=tmp_path)
    assert i18n.resolve_locale("fr") == "fr"  # same stored "fr" now resolves once re-enabled


# --- invariants against the REAL shipped catalogs ---------------------------
# `tests/conftest.py` reconfigures `core.i18n` against the real catalogs before every
# test (autouse), so each test below starts clean regardless of what ran before it —
# no extra fixture needed here to undo the tmp_path catalogs used further up.
def _real_catalog(code: str) -> dict[str, object]:
    raw = json.loads((_REAL_LOCALES_DIR / f"{code}.json").read_text(encoding="utf-8"))
    return cast(dict[str, object], raw)


def test_real_catalogs_load_cleanly() -> None:
    i18n.configure("en")
    codes = {m.code for m in i18n.list_enabled_locales()}
    assert codes == {"en", "ar"}


def test_real_catalogs_en_ar_have_full_key_parity() -> None:
    """Not required by configure() (ar may be a subset) — but for this launch every
    key should actually be translated, not silently falling back to English."""
    en_keys = {k for k in _real_catalog("en") if not k.startswith("_")}
    ar_keys = {k for k in _real_catalog("ar") if not k.startswith("_")}
    assert en_keys == ar_keys


def test_real_catalogs_never_use_translate_reserved_placeholder_names() -> None:
    """Regression test: ``translate(key, locale, **kwargs)`` — a template using
    ``{key}`` or ``{locale}`` as its own placeholder collides with those parameter
    names the moment a caller passes that name as a kwarg (found + fixed in
    ``admin.setting_set.*`` during Sprint 11.5: ``key=`` collided with translate's
    own first positional parameter, named ``key``)."""
    formatter = string.Formatter()
    reserved = {"key", "locale"}
    for code in ("en", "ar"):
        for catalog_key, value in _real_catalog(code).items():
            if catalog_key == "_meta" or not isinstance(value, str):
                continue
            fields = {name for _, name, _, _ in formatter.parse(value) if name}
            offending = fields & reserved
            assert not offending, (
                f"{code}.json[{catalog_key!r}] uses reserved placeholder {offending}"
            )


def test_real_error_and_notification_keys_present() -> None:
    """A light smoke check that the drift-prone, hand-maintained key sets referenced
    by domain/exceptions.py and services/notification_service.py actually exist."""
    i18n.configure("en")
    for key in (
        "notification.preparing",
        "notification.failed",
        "language.change_button",
        "language.picker_prompt",
        "language.updated",
    ):
        assert i18n.translate(key, "en") != key
