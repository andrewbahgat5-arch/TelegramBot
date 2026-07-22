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


# --- placeholder-set validation (V2-D-026, Sprint V2.0) ---------------------
def test_configure_rejects_alien_placeholder_in_non_default_locale(tmp_path: Path) -> None:
    """A translation referencing a placeholder the default template lacks fails boot —
    it would otherwise surface to users as a raw ``{...}`` template."""
    _write_catalog(tmp_path, "en", {"_meta": _meta("en"), "greet": "Hi, {name}!"})
    _write_catalog(
        tmp_path, "ar", {"_meta": _meta("ar", direction="rtl"), "greet": "مرحبا، {naem}!"}
    )
    with pytest.raises(i18n.LocaleCatalogError, match="naem"):
        i18n.configure("en", locales_dir=tmp_path)


def test_configure_allows_translation_to_omit_a_placeholder(tmp_path: Path) -> None:
    """Subset is fine: a translation may drop a placeholder, just never invent one."""
    _write_catalog(tmp_path, "en", {"_meta": _meta("en"), "greet": "Hi {name}, {count} new"})
    _write_catalog(tmp_path, "ar", {"_meta": _meta("ar", direction="rtl"), "greet": "مرحبا {name}"})
    i18n.configure("en", locales_dir=tmp_path)  # must not raise
    assert i18n.translate("greet", "ar", name="X", count=3) == "مرحبا X"


def test_configure_ignores_format_spec_and_escapes_in_placeholder_check(tmp_path: Path) -> None:
    """Format specs (``{n:>5}``), conversions, and ``{{``/``}}`` escapes are not
    alien placeholders."""
    _write_catalog(tmp_path, "en", {"_meta": _meta("en"), "k": "{n} items"})
    _write_catalog(
        tmp_path, "ar", {"_meta": _meta("ar", direction="rtl"), "k": "{{}} {n!r} {n:>3}"}
    )
    i18n.configure("en", locales_dir=tmp_path)  # must not raise


def test_real_catalogs_pass_placeholder_validation() -> None:
    """Acceptance: the shipped en/ar catalogs boot cleanly under the new check."""
    i18n.configure("en")  # raises if ar introduced an alien placeholder


# --- per-locale coverage metric (V2-D-026, Sprint V2.0) ---------------------
def test_coverage_default_locale_is_one(tmp_path: Path) -> None:
    _write_catalog(tmp_path, "en", {"_meta": _meta("en"), "a": "A", "b": "B"})
    i18n.configure("en", locales_dir=tmp_path)
    assert i18n.catalog_coverage()["en"] == 1.0


def test_coverage_reflects_partial_translation(tmp_path: Path) -> None:
    _write_catalog(tmp_path, "en", {"_meta": _meta("en"), "a": "A", "b": "B", "c": "C", "d": "D"})
    _write_catalog(tmp_path, "ar", {"_meta": _meta("ar", direction="rtl"), "a": "أ", "b": "ب"})
    i18n.configure("en", locales_dir=tmp_path)
    assert i18n.catalog_coverage()["ar"] == 0.5  # 2 of 4 user-facing keys


def test_coverage_carves_out_admin_namespaces(tmp_path: Path) -> None:
    """Admin/owner-only keys are excluded from the denominator, so leaving them
    untranslated does not depress a locale's user-facing coverage."""
    _write_catalog(
        tmp_path,
        "en",
        {"_meta": _meta("en"), "a": "A", "panel.x": "X", "admin.y": "Y", "cookies.z": "Z"},
    )
    # ar translates only the one user-facing key "a" -> full user-facing coverage.
    _write_catalog(tmp_path, "ar", {"_meta": _meta("ar", direction="rtl"), "a": "أ"})
    i18n.configure("en", locales_dir=tmp_path)
    assert i18n.catalog_coverage()["ar"] == 1.0


def test_real_catalogs_report_full_coverage() -> None:
    """en/ar are at full key parity, so both report 1.0."""
    i18n.configure("en")
    coverage = i18n.catalog_coverage()
    assert coverage["en"] == 1.0
    assert coverage["ar"] == 1.0


def test_configure_publishes_coverage_to_metric_gauge() -> None:
    """The composition root wires catalog_coverage() into the i18n_catalog_coverage
    gauge; exercise that path and confirm the series is exposed."""
    from core import metrics

    i18n.configure("en")
    metrics.set_i18n_coverage(i18n.catalog_coverage())
    body, _ = metrics.render()
    assert b"i18n_catalog_coverage" in body
