"""NotificationService (MASTER_PLAN Component 9.2, Task 6.9 + UX follow-up + Sprint 11.5 i18n).

User-facing job messaging. The pipeline has several internal stages (download,
transcode, upload), but the user only ever sees **one clean status line** — the same
single emoji + text style used by the analysis stage (``🔍 Analyzing link…``), for a
consistent progress design across both stages (item #6). Internal stage names are not
surfaced (Owner UX request); the line finishes by being deleted on ✅ or edited to ❌.

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


def _progress_text(locale: str) -> str:
    """The single clean status line shown while a job runs (item #6 — matches the
    analysis stage's ``🔍 Analyzing link…`` style: one emoji + text, no block bar)."""
    return translate("notification.preparing", locale)


class NotificationService:
    def __init__(self, sender: MessageSenderProtocol) -> None:
        self._sender = sender

    async def send_initial(
        self, chat_id: int, locale: str, stage: ProgressStage = ProgressStage.QUEUED
    ) -> int:
        """Send the first progress message; return its id for later in-place edits."""
        return await self._sender.send_message(chat_id, _progress_text(locale))

    async def notify_stage(
        self, chat_id: int, message_id: int, stage: ProgressStage, locale: str
    ) -> None:
        """No-op: the progress message is a single static status line (item #6), so
        internal stage transitions no longer re-render it. Kept for call-site
        compatibility (``DownloadService`` reports stages) and as the hook if a future
        design reintroduces per-stage text."""
        return None

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
