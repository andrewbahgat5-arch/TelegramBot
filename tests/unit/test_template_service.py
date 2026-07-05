"""Unit tests for services/template_service.py + core.i18n override hook (Sprint 13.8)."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

import pytest

from core import i18n
from services.template_service import TemplateService

pytestmark = pytest.mark.asyncio


class _Row:
    def __init__(self, key: str, locale: str, content: str) -> None:
        self.key = key
        self.locale = locale
        self.content = content
        self.updated_at = datetime.datetime(2026, 7, 5, tzinfo=datetime.UTC)


class FakeTemplateStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], _Row] = {}

    async def load_all(self) -> list[_Row]:
        return list(self.rows.values())

    async def get(self, key: str, locale: str) -> _Row | None:
        return self.rows.get((key, locale))

    async def upsert(
        self, key: str, locale: str, content: str, *, updated_by: int | None = None
    ) -> None:
        self.rows[(key, locale)] = _Row(key, locale, content)

    async def delete_template(self, key: str, locale: str) -> None:
        self.rows.pop((key, locale), None)


def _configure_temp_catalog(tmp_path: Path) -> None:
    catalog: dict[str, Any] = {
        "_meta": {
            "code": "en",
            "native_name": "English",
            "direction": "ltr",
            "enabled": True,
            "version": 1,
        },
        "user.welcome": "Welcome {name}!",
        "user.help": "Default help text.",
    }
    (tmp_path / "en.json").write_text(json.dumps(catalog), encoding="utf-8")
    i18n.configure("en", locales_dir=tmp_path)


async def test_set_get_reset_roundtrip() -> None:
    svc = TemplateService(FakeTemplateStore())
    assert await svc.get("welcome", "en") is None
    await svc.set("welcome", "en", "Hi {name}", updated_by=1)
    assert await svc.get("welcome", "en") == "Hi {name}"
    await svc.reset("welcome", "en")
    assert await svc.get("welcome", "en") is None


async def test_set_unknown_key_rejected() -> None:
    svc = TemplateService(FakeTemplateStore())
    with pytest.raises(KeyError):
        await svc.set("not_a_template", "en", "x", updated_by=1)


async def test_custom_template_overrides_translate(tmp_path: Path) -> None:
    _configure_temp_catalog(tmp_path)
    svc = TemplateService(FakeTemplateStore())

    assert i18n.translate("user.welcome", "en", name="Ahmed") == "Welcome Ahmed!"
    await svc.set("welcome", "en", "Marhaba {name} 👋", updated_by=1)
    assert i18n.translate("user.welcome", "en", name="Ahmed") == "Marhaba Ahmed 👋"


async def test_reset_reverts_translate_to_default(tmp_path: Path) -> None:
    _configure_temp_catalog(tmp_path)
    svc = TemplateService(FakeTemplateStore())
    await svc.set("welcome", "en", "Custom {name}", updated_by=1)
    await svc.reset("welcome", "en")
    assert i18n.translate("user.welcome", "en", name="Sara") == "Welcome Sara!"


async def test_catalog_template_ignores_overrides(tmp_path: Path) -> None:
    _configure_temp_catalog(tmp_path)
    svc = TemplateService(FakeTemplateStore())
    await svc.set("welcome", "en", "Overridden {name}", updated_by=1)
    # The shipped default is still reachable for the preview screen.
    assert i18n.catalog_template("user.welcome", "en") == "Welcome {name}!"


async def test_load_warms_cache_and_overrides(tmp_path: Path) -> None:
    _configure_temp_catalog(tmp_path)
    store = FakeTemplateStore()
    store.rows[("welcome", "en")] = _Row("welcome", "en", "Preloaded {name}")
    svc = TemplateService(store)

    await svc.load()

    assert await svc.get("welcome", "en") == "Preloaded {name}"
    assert i18n.translate("user.welcome", "en", name="Omar") == "Preloaded Omar"


async def test_list_all_marks_custom_vs_default(tmp_path: Path) -> None:
    _configure_temp_catalog(tmp_path)
    svc = TemplateService(FakeTemplateStore())
    await svc.set("welcome", "en", "Custom welcome", updated_by=1)

    views = {v.key: v for v in await svc.list_all("en")}

    assert views["welcome"].is_custom is True
    assert views["welcome"].content_preview == "Custom welcome"
    assert views["help"].is_custom is False
    assert views["help"].content_preview == "Default help text."
    assert len(views) == 9  # every editable key present
