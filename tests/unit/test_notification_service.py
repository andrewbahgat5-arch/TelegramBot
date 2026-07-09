"""Unit tests for NotificationService progress messaging (MASTER_PLAN Task 6.9 + UX)."""

from __future__ import annotations

from services.notification_service import NotificationService, ProgressStage
from tests.unit._fakes import FakeMessageSender


async def test_send_initial_shows_one_clean_status_line() -> None:
    # Item #6: a single clean status line (analysis-stage style), no block/percentage bar.
    sender = FakeMessageSender()
    service = NotificationService(sender)

    message_id = await service.send_initial(chat_id=10, locale="en")

    assert isinstance(message_id, int)
    assert len(sender.sent) == 1
    text = sender.sent[0][1]
    assert "Preparing your file" in text  # one neutral label, no internal stage names
    assert "%" not in text and "█" not in text and "░" not in text  # no progress bar


async def test_stage_transitions_do_not_rerender_the_line() -> None:
    # The status line is static; stage transitions are a no-op (no wasteful edits).
    sender = FakeMessageSender()
    service = NotificationService(sender)

    for stage in (ProgressStage.DOWNLOADING, ProgressStage.PROCESSING, ProgressStage.UPLOADING):
        await service.notify_stage(chat_id=10, message_id=99, stage=stage, locale="en")

    assert sender.edits == []  # no per-stage edits at all


async def test_completed_and_failed_edits() -> None:
    sender = FakeMessageSender()
    service = NotificationService(sender)

    await service.notify_completed(chat_id=1, message_id=2, locale="en")
    await service.notify_failed(chat_id=1, message_id=2, locale="en")
    await service.notify_failed(chat_id=1, message_id=2, locale="en", reason="too large")

    assert len(sender.deletes) == 1
    assert sender.deletes[0] == (1, 2)
    assert sender.edits[0][2].startswith("❌")
    assert "too large" in sender.edits[1][2]
