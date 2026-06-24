"""Unit tests for BroadcastWorker (MASTER_PLAN Task 8.1, flow 16.8)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from tests.unit._fakes import FakeBroadcastRepo, FakeUser, FakeUserRepo
from workers.broadcast_worker import BroadcastWorker


class _FakeSession:
    """A no-op async session: the fakes ignore it; only ``commit`` is awaited."""

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def commit(self) -> None:
        return None


class _Sender:
    """A ``MessageSenderProtocol`` that records sends and fails for chosen chats."""

    def __init__(self, fail_for: Iterable[int] = ()) -> None:
        self.sent: list[tuple[int, str]] = []
        self._fail_for = set(fail_for)

    async def send_message(self, chat_id: int, text: str) -> int:
        if chat_id in self._fail_for:
            raise RuntimeError("bot was blocked by the user")
        self.sent.append((chat_id, text))
        return 1

    async def edit_message(self, chat_id: int, message_id: int, text: str) -> None:
        return None


def _build(
    *, sender: _Sender, chunk_size: int = 2
) -> tuple[BroadcastWorker, FakeBroadcastRepo, FakeUserRepo]:
    broadcasts = FakeBroadcastRepo()
    users = FakeUserRepo()
    worker = BroadcastWorker(
        session_factory=lambda: _FakeSession(),  # type: ignore[arg-type]
        build_broadcast_repo=lambda s: broadcasts,
        build_user_repo=lambda s: users,
        sender=sender,
        chunk_size=chunk_size,
    )
    return worker, broadcasts, users


def _seed_audience(users: FakeUserRepo) -> None:
    users.by_tid[101] = FakeUser(id=1, telegram_id=101, role="user", language="en")
    users.by_tid[102] = FakeUser(id=2, telegram_id=102, role="user", language="en")
    users.by_tid[103] = FakeUser(id=3, telegram_id=103, role="user", language="en")
    users.by_tid[104] = FakeUser(id=4, telegram_id=104, is_banned=True)  # never targeted


async def _queue(broadcasts: FakeBroadcastRepo, **kw: Any) -> Any:
    return await broadcasts.create_pending(
        created_by=1,
        message_text=kw.get("text", "hello"),
        target_language=kw.get("language"),
        target_role=kw.get("role"),
        expected_total=kw.get("expected_total", 0),
    )


async def test_run_once_fans_out_to_all_in_chunks() -> None:
    sender = _Sender()
    worker, broadcasts, users = _build(sender=sender, chunk_size=2)
    _seed_audience(users)
    row = await _queue(broadcasts)

    handled = await worker.run_once()

    assert handled is True
    assert sorted(chat for chat, _ in sender.sent) == [101, 102, 103]  # banned excluded
    assert row.status == "completed" and row.completed_at is not None
    assert row.total_sent == 3 and row.total_failed == 0


async def test_run_once_counts_failures_without_aborting() -> None:
    sender = _Sender(fail_for={102})  # one recipient blocks the bot
    worker, broadcasts, users = _build(sender=sender)
    _seed_audience(users)
    row = await _queue(broadcasts)

    await worker.run_once()

    assert [chat for chat, _ in sender.sent] == [101, 103]  # 102 failed, others still sent
    assert row.total_sent == 2 and row.total_failed == 1
    assert row.status == "completed"


async def test_run_once_respects_role_filter() -> None:
    sender = _Sender()
    worker, broadcasts, users = _build(sender=sender)
    _seed_audience(users)
    users.by_tid[103].role = "moderator"
    await _queue(broadcasts, role="moderator")

    await worker.run_once()

    assert [chat for chat, _ in sender.sent] == [103]


async def test_run_once_returns_false_when_nothing_pending() -> None:
    sender = _Sender()
    worker, _, _ = _build(sender=sender)
    assert await worker.run_once() is False
    assert sender.sent == []
