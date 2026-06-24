"""File-delivery and message protocols (MASTER_PLAN Task 6.1, Component 9.5).

The download pipeline never touches the Telegram client directly — it depends on
these ports, satisfied by ``infrastructure/telegram/file_sender.py`` (Section 8).

* :class:`FileSenderProtocol` — upload a local file once to obtain a reusable
  ``file_id`` (flow 16.1 W4), and deliver a cached file by ``file_id`` (W7 / 16.2).
* :class:`MessageSenderProtocol` — the raw message transport ``NotificationService``
  uses for progress edits (Component 9.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from domain.enums import MediaFormat, Quality


@dataclass(frozen=True, slots=True)
class UploadedFile:
    """The reusable Telegram references produced by a one-time upload (10.4)."""

    file_id: str
    unique_file_id: str
    size_bytes: int | None = None


class FileSenderProtocol(Protocol):
    async def upload(
        self,
        path: Path,
        *,
        format_: MediaFormat,
        quality: Quality,
        chat_id: int,
        filename: str,
        caption: str | None = None,
    ) -> UploadedFile:
        """Upload ``path`` to ``chat_id`` (delivering it) and return its reusable ids.

        The first waiter's upload *is* their delivery, so we never send the file
        twice. ``quality`` selects the audio container's send method.
        """
        ...

    async def send_cached(
        self,
        telegram_id: int,
        file_id: str,
        *,
        format_: MediaFormat,
        quality: Quality,
        caption: str | None = None,
    ) -> None:
        """Deliver an already-uploaded file to ``telegram_id`` by ``file_id``."""
        ...


class MessageSenderProtocol(Protocol):
    async def send_message(self, chat_id: int, text: str) -> int:
        """Send ``text`` to ``chat_id``; return the new message id."""
        ...

    async def edit_message(self, chat_id: int, message_id: int, text: str) -> None:
        """Edit a previously sent message's text (best-effort; ignores 'not modified')."""
        ...
