"""NotificationService (MASTER_PLAN Component 9.2, Task 6.9 + UX follow-up).

User-facing job messaging. The pipeline has several internal stages (download,
transcode, upload), but the user only ever sees **one message with a single progress
bar** that advances in place — internal stage names are not surfaced (Owner UX
request). The bar advances as the job moves through its stages and finishes at ✅ or
❌.

Framework-agnostic: depends on ``MessageSenderProtocol`` (raw text transport),
injected at the composition root. Progress edits are best-effort — a failed edit
(user deleted the message, "not modified") never breaks the pipeline.
"""

from __future__ import annotations

from enum import StrEnum

from domain.protocols.file_sender import MessageSenderProtocol


class ProgressStage(StrEnum):
    """Internal pipeline stages, mapped to a single user-facing percentage."""

    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    UPLOADING = "uploading"


# A coarse percentage per stage — enough to show steady forward motion without
# exposing the underlying step to the user.
_STAGE_PERCENT: dict[ProgressStage, int] = {
    ProgressStage.QUEUED: 5,
    ProgressStage.DOWNLOADING: 35,
    ProgressStage.PROCESSING: 65,
    ProgressStage.UPLOADING: 90,
}

_BAR_WIDTH = 10
_WORKING_LABEL = "⏳ Preparing your file…"
_COMPLETED_TEXT = "✅ Done — here is your file."
_FAILED_TEXT = "❌ Sorry, that download failed. Please try again."


def _bar(percent: int) -> str:
    percent = max(0, min(100, percent))
    filled = round(percent / 100 * _BAR_WIDTH)
    return f"{'█' * filled}{'░' * (_BAR_WIDTH - filled)} {percent}%"


def _progress_text(percent: int) -> str:
    return f"{_WORKING_LABEL}\n{_bar(percent)}"


class NotificationService:
    def __init__(self, sender: MessageSenderProtocol) -> None:
        self._sender = sender

    async def send_initial(self, chat_id: int, stage: ProgressStage = ProgressStage.QUEUED) -> int:
        """Send the first progress message; return its id for later in-place edits."""
        return await self._sender.send_message(chat_id, _progress_text(_STAGE_PERCENT[stage]))

    async def notify_stage(self, chat_id: int, message_id: int, stage: ProgressStage) -> None:
        await self._sender.edit_message(chat_id, message_id, _progress_text(_STAGE_PERCENT[stage]))

    async def notify_text(self, chat_id: int, message_id: int, text: str) -> None:
        """Edit the progress message to an arbitrary status line (e.g. duplicate)."""
        await self._sender.edit_message(chat_id, message_id, text)

    async def notify_completed(self, chat_id: int, message_id: int) -> None:
        await self._sender.edit_message(chat_id, message_id, _COMPLETED_TEXT)

    async def notify_failed(self, chat_id: int, message_id: int, reason: str | None = None) -> None:
        text = f"{_FAILED_TEXT}\n{reason}" if reason else _FAILED_TEXT
        await self._sender.edit_message(chat_id, message_id, text)
