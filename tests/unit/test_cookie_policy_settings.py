"""Unit tests for CookiePolicyProvider — admin-editable pool policy (§13)."""

from __future__ import annotations

from types import SimpleNamespace

from infrastructure.cookies.policy_settings import CookiePolicyProvider
from services.cookie_pool_service import CookiePolicy


class _FakeSession:
    def __init__(self, rows: dict[str, str]) -> None:
        self.rows = rows

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None


def _factory(rows: dict[str, str], *, explode: bool = False):
    session = _FakeSession(rows)

    def make() -> _FakeSession:
        if explode:
            raise RuntimeError("db down")
        return session

    return make


def _patch_repo(monkeypatch, rows: dict[str, str]) -> None:
    class _Repo:
        def __init__(self, _session: object) -> None: ...

        async def get_by_key(self, key: str):
            value = rows.get(key)
            return SimpleNamespace(value=value) if value is not None else None

    monkeypatch.setattr(
        "infrastructure.cookies.policy_settings.SettingsRepository", _Repo
    )


async def test_defaults_apply_when_no_rows_exist(monkeypatch) -> None:
    _patch_repo(monkeypatch, {})
    policy = await CookiePolicyProvider(_factory({})).get()
    assert policy == CookiePolicy()


async def test_admin_values_override_every_knob(monkeypatch) -> None:
    rows = {
        "cookie_selection_strategy": "round_robin",
        "cookie_max_concurrent_leases": "3",
        "cookie_warning_threshold": "5",
        "cookie_cooldown_threshold": "7",
        "cookie_cooldown_seconds": "60",
        "cookie_cooldown_max_seconds": "600",
        "cookie_max_cooldown_cycles": "9",
        "cookie_lease_ttl_seconds": "120",
        "cookie_allow_affinity_break": "true",
    }
    _patch_repo(monkeypatch, rows)
    policy = await CookiePolicyProvider(_factory(rows)).get()
    assert policy.strategy == "round_robin"
    assert policy.max_concurrent_leases == 3
    assert policy.warning_threshold == 5
    assert policy.cooldown_threshold == 7
    assert policy.cooldown_seconds == 60
    assert policy.cooldown_max_seconds == 600
    assert policy.max_cooldown_cycles == 9
    assert policy.lease_ttl_seconds == 120
    assert policy.allow_affinity_break is True


async def test_unknown_strategy_falls_back_to_the_default(monkeypatch) -> None:
    rows = {"cookie_selection_strategy": "banana"}
    _patch_repo(monkeypatch, rows)
    policy = await CookiePolicyProvider(_factory(rows)).get()
    assert policy.strategy == "lru"  # a typo must not disable selection


async def test_non_numeric_value_is_ignored(monkeypatch) -> None:
    rows = {"cookie_max_concurrent_leases": "lots"}
    _patch_repo(monkeypatch, rows)
    policy = await CookiePolicyProvider(_factory(rows)).get()
    assert policy.max_concurrent_leases == 1


async def test_zero_lease_cap_is_clamped_so_the_pool_cannot_be_switched_off(
    monkeypatch,
) -> None:
    # A 0 here would make every acquire fail and silently stop using cookies at all.
    rows = {"cookie_max_concurrent_leases": "0"}
    _patch_repo(monkeypatch, rows)
    policy = await CookiePolicyProvider(_factory(rows)).get()
    assert policy.max_concurrent_leases == 1


async def test_settings_failure_keeps_the_last_good_policy(monkeypatch) -> None:
    _patch_repo(monkeypatch, {})
    provider = CookiePolicyProvider(_factory({}, explode=True))
    policy = await provider.get()
    assert policy == CookiePolicy()  # defaults, and no exception escaped


async def test_values_are_cached_between_calls(monkeypatch) -> None:
    calls = {"n": 0}

    class _Repo:
        def __init__(self, _session: object) -> None: ...

        async def get_by_key(self, key: str):
            calls["n"] += 1
            return None

    monkeypatch.setattr(
        "infrastructure.cookies.policy_settings.SettingsRepository", _Repo
    )
    provider = CookiePolicyProvider(_factory({}), cache_ttl=60)
    await provider.get()
    first = calls["n"]
    await provider.get()
    assert calls["n"] == first  # second call served from cache
