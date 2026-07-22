"""Entitlement registry (VERSION_2_MASTER_PLAN §5.2, V2-D-004/005/020).

The typed key registry every plan's ``entitlements`` JSONB is validated against at
startup. **Keys are architecture; values are seed data** (V2-D-020) — no value appears
here. Business logic's only legal read is ``ResolvedEntitlements.<field>``; the plan
forbids ``if is_premium`` / ``if plan_code == "premium"`` the same way (V2-D-005).

Startup validation fails the boot on an unknown key, a missing key, or a wrong type —
the same fail-fast philosophy as the locale-catalog guard (``core/i18n.py``). That makes
a malformed plan a deploy-time error, never a silent runtime surprise.

V2.1 ships only the keys a consumer reads *now* (the shadow-parity surface) plus the
reserved ``playlists_enabled``. Later keys (``batch_max_links``, ``max_concurrent_jobs``,
``max_video_height``, ``audio_formats``, ``priority_band``) are added by the sprint that
consumes each — a key with no consumer is an unvalidated guess. Adding one later is a
single :data:`REGISTRY` entry + a seed value, never a migration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, cast


class EntitlementError(Exception):
    """Raised when a plan's entitlements do not satisfy the registry (fail fast)."""


@dataclass(frozen=True, slots=True)
class EntitlementKey:
    """One registry entry: the key name and the Python type its value must be."""

    name: str
    type_: type


# The V2.1 registry. bool is intentionally listed before int in checks (bool is an int
# subclass in Python — a bool must never satisfy an int key, nor an int a bool key).
REGISTRY: Final[tuple[EntitlementKey, ...]] = (
    EntitlementKey("daily_download_limit", int),
    EntitlementKey("cooldown_seconds", int),
    # Bytes, not MB (the plan says "max_file_size_mb"): the live settings this seeds
    # from — free_max_file_size / premium_max_file_size — are byte-valued, so bytes
    # keeps the seed a lossless direct copy and matches the global max_file_size unit.
    EntitlementKey("max_file_size_bytes", int),
    EntitlementKey("ad_free", bool),
    EntitlementKey("playlists_enabled", bool),  # reserved; seeded false on every plan
)

_KEYS_BY_NAME: Final[dict[str, EntitlementKey]] = {k.name: k for k in REGISTRY}


@dataclass(frozen=True, slots=True)
class ResolvedEntitlements:
    """A user's effective entitlements — the only object business logic reads.

    Built exclusively via :meth:`from_mapping` from a validated plan's JSONB, so every
    field is guaranteed present and correctly typed by the time anything reads it.
    """

    daily_download_limit: int
    cooldown_seconds: int
    max_file_size_bytes: int
    ad_free: bool
    playlists_enabled: bool

    @classmethod
    def from_mapping(cls, entitlements: Mapping[str, object]) -> ResolvedEntitlements:
        """Build from an already-:func:`validate`-d entitlements mapping.

        The casts are sound because :func:`validate` has already proven each value's type
        (this is only ever called on a mapping that passed validation at load time).
        """
        return cls(
            daily_download_limit=cast(int, entitlements["daily_download_limit"]),
            cooldown_seconds=cast(int, entitlements["cooldown_seconds"]),
            max_file_size_bytes=cast(int, entitlements["max_file_size_bytes"]),
            ad_free=cast(bool, entitlements["ad_free"]),
            playlists_enabled=cast(bool, entitlements["playlists_enabled"]),
        )


def validate(plan_code: str, entitlements: Mapping[str, object]) -> None:
    """Validate one plan's entitlements against :data:`REGISTRY`, or raise.

    Fails on an unknown key, a missing key, or a wrong-typed value. ``plan_code`` is
    only used to make the error message point at the offending plan.
    """
    unknown = set(entitlements) - set(_KEYS_BY_NAME)
    if unknown:
        raise EntitlementError(
            f"plan {plan_code!r}: unknown entitlement key(s) {sorted(unknown)} "
            f"(registry keys: {sorted(_KEYS_BY_NAME)})"
        )
    for key in REGISTRY:
        if key.name not in entitlements:
            raise EntitlementError(f"plan {plan_code!r}: missing entitlement key {key.name!r}")
        value = entitlements[key.name]
        if not _type_matches(value, key.type_):
            raise EntitlementError(
                f"plan {plan_code!r}: entitlement {key.name!r} must be {key.type_.__name__}, "
                f"got {type(value).__name__} ({value!r})"
            )


def _type_matches(value: object, expected: type) -> bool:
    """Type check that never conflates ``bool`` with ``int`` (bool ⊂ int in Python)."""
    if expected is bool:
        return isinstance(value, bool)
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, expected)
