"""Cookie policy settings adapter (DESIGN_COOKIE_POOL.md §13, Owner point 6).

Reads the tunable pool policy from the admin-editable ``settings`` table so the six
knobs — strategy, cooldown, lease cap, thresholds, retry intervals — can be retuned from
the panel without a redeploy. Mirrors ``ProviderSettingsAdapter``: the pool is a
long-lived singleton, so this opens a short-lived read session per refresh rather than
borrowing a request session.

Values are cached for a short TTL. Selection happens on every YouTube request, and
hitting Postgres for eleven settings each time would be pointless load — a stale value
for a few seconds is harmless for a policy knob.
"""

from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.logging import get_logger
from infrastructure.database.repositories.setting import SettingsRepository
from services.cookie_pool_service import CookiePolicy

_log = get_logger("infrastructure.cookies.policy_settings")

#: Setting key -> attribute on :class:`CookiePolicy`. Keys are seeded by migration
#: 2026071802; an absent row falls back to the dataclass default.
_INT_KEYS: dict[str, str] = {
    "cookie_max_concurrent_leases": "max_concurrent_leases",
    "cookie_warning_threshold": "warning_threshold",
    "cookie_cooldown_threshold": "cooldown_threshold",
    "cookie_cooldown_seconds": "cooldown_seconds",
    "cookie_cooldown_max_seconds": "cooldown_max_seconds",
    "cookie_max_cooldown_cycles": "max_cooldown_cycles",
    "cookie_lease_ttl_seconds": "lease_ttl_seconds",
}
_STR_KEYS: dict[str, str] = {"cookie_selection_strategy": "strategy"}
_BOOL_KEYS: dict[str, str] = {"cookie_allow_affinity_break": "allow_affinity_break"}

_VALID_STRATEGIES = frozenset({"lru", "round_robin", "weighted", "sticky"})
_TRUE = frozenset({"true", "1", "yes", "on"})

#: Selection runs per request; a few seconds of staleness on a policy knob is fine.
_CACHE_TTL_SECONDS = 30.0


class CookiePolicyProvider:
    """Supplies a fresh :class:`CookiePolicy`, cached briefly."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        cache_ttl: float = _CACHE_TTL_SECONDS,
    ) -> None:
        self._sessions = session_factory
        self._ttl = cache_ttl
        self._cached = CookiePolicy()
        self._loaded_at = 0.0

    async def get(self) -> CookiePolicy:
        now = time.monotonic()
        if now - self._loaded_at < self._ttl:
            return self._cached
        try:
            self._cached = await self._load()
        except Exception as exc:
            # A settings hiccup must never stop cookie selection — keep the last good
            # policy (or the defaults) and try again after the TTL.
            _log.warning("cookie_policy_load_failed", error=str(exc))
        self._loaded_at = now
        return self._cached

    async def _load(self) -> CookiePolicy:
        keys = [*_INT_KEYS, *_STR_KEYS, *_BOOL_KEYS]
        async with self._sessions() as session:
            repo = SettingsRepository(session)
            rows = {key: await repo.get_by_key(key) for key in keys}

        values: dict[str, object] = {}
        defaults = CookiePolicy()
        for key, attr in _INT_KEYS.items():
            row = rows.get(key)
            if row is None:
                continue
            try:
                parsed = int(row.value)
            except (TypeError, ValueError):
                _log.warning("cookie_policy_bad_int", key=key, value=row.value)
                continue
            # A non-positive lease cap or threshold would disable selection entirely;
            # clamp rather than let a typo take the pool offline.
            values[attr] = max(parsed, 1) if attr != "cooldown_seconds" else max(parsed, 0)

        row = rows.get("cookie_selection_strategy")
        if row is not None:
            strategy = str(row.value).strip().lower()
            if strategy in _VALID_STRATEGIES:
                values["strategy"] = strategy
            else:
                _log.warning("cookie_policy_bad_strategy", value=row.value)

        row = rows.get("cookie_allow_affinity_break")
        if row is not None:
            values["allow_affinity_break"] = str(row.value).strip().lower() in _TRUE

        merged = {
            "strategy": values.get("strategy", defaults.strategy),
            "max_concurrent_leases": values.get(
                "max_concurrent_leases", defaults.max_concurrent_leases
            ),
            "warning_threshold": values.get("warning_threshold", defaults.warning_threshold),
            "cooldown_threshold": values.get("cooldown_threshold", defaults.cooldown_threshold),
            "cooldown_seconds": values.get("cooldown_seconds", defaults.cooldown_seconds),
            "cooldown_max_seconds": values.get(
                "cooldown_max_seconds", defaults.cooldown_max_seconds
            ),
            "max_cooldown_cycles": values.get(
                "max_cooldown_cycles", defaults.max_cooldown_cycles
            ),
            "lease_ttl_seconds": values.get("lease_ttl_seconds", defaults.lease_ttl_seconds),
            "allow_affinity_break": values.get(
                "allow_affinity_break", defaults.allow_affinity_break
            ),
        }
        return CookiePolicy(**merged)  # type: ignore[arg-type]
