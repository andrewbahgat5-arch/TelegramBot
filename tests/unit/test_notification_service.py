"""Unit tests for NotificationService single-bar progress (MASTER_PLAN Task 6.9 + UX)."""

from __future__ import annotations

from services.notification_service import NotificationService, ProgressStage
from tests.unit._fakes import FakeMessageSender


async def test_send_initial_returns_id_and_shows_one_progress_bar() -> None:
    sender = FakeMessageSender()
    service = NotificationService(sender)

    message_id = await service.send_initial(chat_id=10)

    assert isinstance(message_id, int)
    assert len(sender.sent) == 1
    text = sender.sent[0][1]
    assert "Preparing your file" in text  # one neutral label, no internal stage names
    assert "%" in text  # a percentage bar


async def test_stage_advances_the_percentage_in_place() -> None:
    sender = FakeMessageSender()
    service = NotificationService(sender)

    for stage in (ProgressStage.DOWNLOADING, ProgressStage.PROCESSING, ProgressStage.UPLOADING):
        await service.notify_stage(chat_id=10, message_id=99, stage=stage)

    percents = [int(e[2].split()[-1].rstrip("%")) for e in sender.edits]
    assert percents == sorted(percents)  # monotonically increasing
    assert percents[-1] == 90
    # Internal stage names are never shown to the user.
    assert all("Downloading" not in e[2] and "Processing" not in e[2] for e in sender.edits)


async def test_completed_and_failed_edits() -> None:
    sender = FakeMessageSender()
    service = NotificationService(sender)

    await service.notify_completed(chat_id=1, message_id=2)
    await service.notify_failed(chat_id=1, message_id=2)
    await service.notify_failed(chat_id=1, message_id=2, reason="too large")

    assert sender.edits[0][2].startswith("✅")
    assert sender.edits[1][2].startswith("❌")
    assert "too large" in sender.edits[2][2]
