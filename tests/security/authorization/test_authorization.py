"""Security · Authentication & Authorization (MASTER_PLAN §25.9.2).

Role gating must deny privilege escalation, and forged/cross-signed callbacks
must fail HMAC verification.
"""

from __future__ import annotations

from types import SimpleNamespace

from bot.callbacks.factory import CallbackSigner
from bot.filters.role_filter import RoleFilter, StaffFilter
from domain.enums import UserRole

_EVENT = SimpleNamespace()  # RoleFilter only needs `user`; the event is unused.


def _user(role: UserRole) -> SimpleNamespace:
    return SimpleNamespace(role=role)


# --- Role gating ----------------------------------------------------------
async def test_plain_user_denied_owner_only() -> None:
    owner_only = RoleFilter(UserRole.OWNER)
    assert await owner_only(_EVENT, user=_user(UserRole.USER)) is False


async def test_moderator_denied_owner_only() -> None:
    owner_only = RoleFilter(UserRole.OWNER)
    assert await owner_only(_EVENT, user=_user(UserRole.MODERATOR)) is False


async def test_owner_allowed_owner_only() -> None:
    owner_only = RoleFilter(UserRole.OWNER)
    assert await owner_only(_EVENT, user=_user(UserRole.OWNER)) is True


async def test_staff_filter_admits_moderator_denies_user() -> None:
    assert await StaffFilter(_EVENT, user=_user(UserRole.MODERATOR)) is True
    assert await StaffFilter(_EVENT, user=_user(UserRole.USER)) is False


async def test_missing_user_denied() -> None:
    assert await RoleFilter(UserRole.USER)(_EVENT, user=None) is False


# --- Forged callback escalation -------------------------------------------
def test_forged_panel_callback_rejected() -> None:
    signer = CallbackSigner("owner-secret")
    legit = signer.pack_panel("usr", "ban", arg=42)
    # Retarget the action while keeping the original signature.
    parts = legit.split("|")
    parts[2] = "del"
    assert signer.unpack_panel("|".join(parts)) is None


def test_callback_signed_with_other_secret_rejected() -> None:
    attacker = CallbackSigner("attacker-secret")
    server = CallbackSigner("server-secret")
    forged = attacker.pack_panel("usr", "ban", arg=42)
    assert server.unpack_panel(forged) is None


def test_legit_panel_callback_roundtrips() -> None:
    signer = CallbackSigner("owner-secret")
    parsed = signer.unpack_panel(signer.pack_panel("usr", "ban", arg=42, value=7))
    assert parsed is not None
    assert (parsed.section, parsed.action, parsed.arg, parsed.value) == ("usr", "ban", 42, 7)
