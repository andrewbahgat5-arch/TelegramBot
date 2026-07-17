"""Unit tests for AdminNotificationService (admin/owner event notifications)."""

from __future__ import annotations

import datetime
from dataclasses import dataclass

import pytest

from domain.entities.user import UserSnapshot
from domain.enums import UserRole
from services.admin_notification_service import AdminNotificationService

pytestmark = pytest.mark.asyncio


@dataclass
class _Staff:
    telegram_id: int
    language: str | None


class _Sender:
    def __init__(self, fail_for: set[int] | None = None) -> None:
        self.sent: list[tuple[int, str]] = []
        self.parse_modes: list[str | None] = []
        self._fail_for = fail_for or set()

    async def send_message(self, chat_id: int, text: str, *, parse_mode: str | None = None) -> int:
        if chat_id in self._fail_for:
            raise RuntimeError("blocked")
        self.sent.append((chat_id, text))
        self.parse_modes.append(parse_mode)
        return 1

    async def edit_message(self, chat_id: int, message_id: int, text: str) -> None: ...
    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        return True


class _Repo:
    def __init__(self, staff: list[_Staff], *, total: int = 0, blocked: int = 0) -> None:
        self._staff = staff
        self._total = total
        self._blocked = blocked

    async def list_staff(self) -> list[_Staff]:
        return self._staff

    async def count_all(self) -> int:
        return self._total

    async def count_blocked(self) -> int:
        return self._blocked


def _user(tid: int, *, name: str | None = "Bahr", username: str | None = None,
          language: str = "ar") -> UserSnapshot:
    return UserSnapshot(
        id=tid, telegram_id=tid, role=UserRole.USER, is_banned=False, is_premium=False,
        daily_download_count=0, daily_download_count_reset_date=datetime.date(2026, 7, 17),
        total_downloads=0, username=username, first_name=name, language=language,
    )


def _svc(sender: _Sender, repo: _Repo) -> AdminNotificationService:
    return AdminNotificationService(sender, repo)  # type: ignore[arg-type]


async def test_new_user_fans_out_to_every_staff_in_their_locale() -> None:
    sender = _Sender()
    svc = _svc(sender, _Repo([_Staff(1, "ar"), _Staff(2, "en")], total=2284))
    await svc.notify_new_user(_user(6512068704, name="Accounty", username="AccountyAdmin"))

    assert {c for c, _ in sender.sent} == {1, 2}
    ar = next(t for c, t in sender.sent if c == 1)
    en = next(t for c, t in sender.sent if c == 2)
    assert "شخص جديد دخل البوت" in ar          # Arabic title for the ar admin
    assert "A new user joined the bot" in en    # English title for the en admin
    assert "@AccountyAdmin" in ar and "6512068704" in ar
    assert "2284" in ar                         # running total
    assert sender.parse_modes == ["HTML", "HTML"]  # HTML so <b>/<code> render, not raw


async def test_blocked_shows_total_blocked() -> None:
    sender = _Sender()
    svc = _svc(sender, _Repo([_Staff(1, "en")], blocked=1229))
    await svc.notify_bot_blocked(_user(6265741218, name="Rajab", language="ar"))
    (_, text), = sender.sent
    assert "blocked the bot" in text and "1229" in text


async def test_banned_includes_admin_and_reason() -> None:
    sender = _Sender()
    svc = _svc(sender, _Repo([_Staff(1, "en")]))
    await svc.notify_user_banned(
        _user(42, name="Spammer"), by_admin=_user(7, name="Owner"), reason="spam"
    )
    (_, text), = sender.sent
    assert "banned" in text and "Owner" in text and "spam" in text


async def test_delivery_is_best_effort() -> None:
    # One recipient blocked the bot; the rest still receive, and no error propagates.
    sender = _Sender(fail_for={1})
    svc = _svc(sender, _Repo([_Staff(1, "en"), _Staff(2, "en")], total=5))
    await svc.notify_new_user(_user(99))
    assert [c for c, _ in sender.sent] == [2]  # only the reachable admin got it


async def test_html_special_chars_escaped() -> None:
    sender = _Sender()
    svc = _svc(sender, _Repo([_Staff(1, "en")], total=1))
    await svc.notify_new_user(_user(3, name="<b>x</b>&y"))
    (_, text), = sender.sent
    assert "&lt;b&gt;x&lt;/b&gt;&amp;y" in text  # user name escaped, not raw HTML
