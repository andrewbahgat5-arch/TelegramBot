"""NotificationService (MASTER_PLAN Component 9.2, Task 6.9 + UX follow-up + Sprint 11.5 i18n).

User-facing job messaging. The pipeline has several internal stages (download,
transcode, upload), but the user only ever sees **one message with a single progress
bar** that advances in place — internal stage names are not surfaced (Owner UX
request). The bar advances as the job moves through its stages and finishes at ✅ or
❌.

Framework-agnostic: depends on ``MessageSenderProtocol`` (raw text transport),
injected at the composition root. Progress edits are best-effort — a failed edit
(user deleted the message, "not modified") never breaks the pipeline.

``locale`` is a required argument on every method that builds its own text: the
caller (``JobService``/``DownloadService``) resolves the *recipient's* locale — in
a fan-out delivery, different waiters can have different languages — this service
never guesses one on its own (Sprint 11.5).
"""

from __future__ import annotations

from enum import StrEnum

from core.i18n import translate
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


def _bar(percent: int) -> str:
    percent = max(0, min(100, percent))
    filled = round(percent / 100 * _BAR_WIDTH)
    return f"{'█' * filled}{'░' * (_BAR_WIDTH - filled)} {percent}%"


def _progress_text(percent: int, locale: str) -> str:
    return f"{translate('notification.preparing', locale)}\n{_bar(percent)}"


class NotificationService:
    def __init__(self, sender: MessageSenderProtocol) -> None:
        self._sender = sender

    async def send_initial(
        self, chat_id: int, locale: str, stage: ProgressStage = ProgressStage.QUEUED
    ) -> int:
        """Send the first progress message; return its id for later in-place edits."""
        return await self._sender.send_message(
            chat_id, _progress_text(_STAGE_PERCENT[stage], locale)
        )

    async def notify_stage(
        self, chat_id: int, message_id: int, stage: ProgressStage, locale: str
    ) -> None:
        await self._sender.edit_message(
            chat_id, message_id, _progress_text(_STAGE_PERCENT[stage], locale)
        )

    async def notify_text(self, chat_id: int, message_id: int, text: str) -> None:
        """Edit the progress message to an arbitrary, already-localized status line
        (e.g. duplicate/busy) — the caller has already resolved + translated it."""
        await self._sender.edit_message(chat_id, message_id, text)

    async def notify_completed(self, chat_id: int, message_id: int, locale: str) -> None:
        deleted = await self._sender.delete_message(chat_id, message_id)
        if not deleted:
            await self._sender.edit_message(chat_id, message_id, "✅")

    async def notify_failed(
        self, chat_id: int, message_id: int, locale: str, reason: str | None = None
    ) -> None:
        failed_text = translate("notification.failed", locale)
        text = f"{failed_text}\n{reason}" if reason else failed_text
        await self._sender.edit_message(chat_id, message_id, text)
