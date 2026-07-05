"""ReferralService (Sprint 13.7) — deep-link referrals with stacking rewards.

Framework-free (MASTER_PLAN §8): depends on the user/referral repository protocols
and a narrow settings reader only. The bot layer parses the ``?start=ref_<CODE>``
payload and notifies the referrer; this service owns the rules and the writes.

Reward model: a successful referral grants ``referral_reward_downloads`` *permanent*
bonus downloads to **both** the referrer and the new user (stacks on the daily
limit, never expires). ``user_id`` arguments are ``users.id`` (DB ids), matching the
``referrals`` foreign keys — the caller resolves a Telegram id to a snapshot first.
"""

from __future__ import annotations

import datetime
import secrets
import string
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from core.logging import get_logger
from domain.protocols.repositories import (
    ReferralRepositoryProtocol,
    UserRepositoryProtocol,
)

_log = get_logger("services.referral_service")

_CODE_ALPHABET = string.ascii_lowercase + string.digits
_CODE_LENGTH = 8
_UNIQUE_ATTEMPTS = 6


class SettingsReader(Protocol):
    """The slice of SettingsService the referral rules read."""

    async def get(self, key: str) -> Any: ...


@dataclass(frozen=True, slots=True)
class ReferralResult:
    """Outcome of processing a ``?start=ref_CODE`` deep link.

    ``reason`` is ``ok`` on success, else ``self_referral`` | ``already_referred`` |
    ``referrer_not_found`` | ``disabled``. The extra fields are populated on success
    so the bot layer can notify the referrer without another round-trip.
    """

    success: bool
    reason: str
    referrer_telegram_id: int | None = None
    referrer_total_referrals: int = 0
    reward_downloads: int = 0


@dataclass(frozen=True, slots=True)
class UserReferralStats:
    referral_code: str
    referral_link: str
    total_invited: int
    total_bonus_downloads: int


@dataclass(frozen=True, slots=True)
class ReferrerEntry:
    user_id: int  # Telegram id (for display / admin actions)
    username: str | None
    first_name: str
    invite_count: int
    rewards_earned: int


@dataclass(frozen=True, slots=True)
class ReferralDashboard:
    total_referrals: int
    referrals_today: int
    referrals_week: int
    referrals_month: int
    total_rewards_granted: int
    top_referrers: list[ReferrerEntry]


def _default_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


class ReferralService:
    def __init__(
        self,
        *,
        user_repo: UserRepositoryProtocol[Any],
        referral_repo: ReferralRepositoryProtocol[Any],
        settings: SettingsReader,
        bot_username: str,
        code_generator: Callable[[], str] | None = None,
    ) -> None:
        self._users = user_repo
        self._referrals = referral_repo
        self._settings = settings
        self._bot_username = bot_username
        self._code_generator = code_generator or _default_code

    async def generate_code(self, user_id: int) -> str:
        """Return the user's referral code, generating a unique one on first call."""
        user = await self._users.get_by_id(user_id)
        existing = getattr(user, "referral_code", None) if user is not None else None
        if existing:
            return str(existing)
        code = await self._unique_code()
        await self._users.set_referral_code(user_id, code)
        return code

    async def _unique_code(self) -> str:
        for _ in range(_UNIQUE_ATTEMPTS):
            code = self._code_generator()
            if await self._users.get_by_referral_code(code) is None:
                return code
        # Extremely unlikely; widen entropy rather than fail the flow.
        return f"{self._code_generator()}{secrets.token_hex(4)}"

    async def process_referral(self, referrer_code: str, new_user_id: int) -> ReferralResult:
        """Apply a referral for a newly-started user. ``new_user_id`` is a ``users.id``."""
        if not bool(await self._settings.get("referral_enabled")):
            return ReferralResult(success=False, reason="disabled")

        referrer = await self._users.get_by_referral_code(referrer_code)
        if referrer is None:
            return ReferralResult(success=False, reason="referrer_not_found")
        if referrer.id == new_user_id:
            return ReferralResult(success=False, reason="self_referral")
        if await self._referrals.exists_for_referred(new_user_id):
            return ReferralResult(success=False, reason="already_referred")

        reward = int(await self._settings.get("referral_reward_downloads"))
        await self._referrals.create(
            referrer_id=referrer.id, referred_id=new_user_id, reward_granted=True
        )
        await self._users.set_referred_by(new_user_id, referrer.id)
        await self._users.add_referral_bonus(referrer.id, reward)
        await self._users.add_referral_bonus(new_user_id, reward)
        total = await self._referrals.count_for_referrer(referrer.id)
        _log.info("referral_processed", referrer_id=referrer.id, referred_id=new_user_id)
        return ReferralResult(
            success=True,
            reason="ok",
            referrer_telegram_id=referrer.telegram_id,
            referrer_total_referrals=total,
            reward_downloads=reward,
        )

    async def get_user_referral_stats(self, user_id: int) -> UserReferralStats:
        """A single user's code, share link, invite count, and accumulated bonus."""
        code = await self.generate_code(user_id)
        user = await self._users.get_by_id(user_id)
        bonus = int(getattr(user, "referral_bonus_downloads", 0)) if user is not None else 0
        total_invited = await self._referrals.count_for_referrer(user_id)
        return UserReferralStats(
            referral_code=code,
            referral_link=self._link(code),
            total_invited=total_invited,
            total_bonus_downloads=bonus,
        )

    async def get_dashboard(self) -> ReferralDashboard:
        """Admin dashboard: totals, period breakdowns, and the top-5 leaderboard."""
        now = datetime.datetime.now(datetime.UTC)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return ReferralDashboard(
            total_referrals=await self._referrals.count_all(),
            referrals_today=await self._referrals.count_since(today),
            referrals_week=await self._referrals.count_since(now - datetime.timedelta(days=7)),
            referrals_month=await self._referrals.count_since(now - datetime.timedelta(days=30)),
            total_rewards_granted=await self._referrals.count_rewarded(),
            top_referrers=await self.get_leaderboard(limit=5),
        )

    async def get_leaderboard(self, *, limit: int = 10) -> list[ReferrerEntry]:
        """Top referrers by invite count."""
        rows = await self._referrals.leaderboard(limit=limit)
        return [
            ReferrerEntry(
                user_id=telegram_id,
                username=username,
                first_name=first_name,
                invite_count=invites,
                rewards_earned=bonus,
            )
            for telegram_id, username, first_name, invites, bonus in rows
        ]

    def _link(self, code: str) -> str:
        return f"https://t.me/{self._bot_username}?start=ref_{code}"
