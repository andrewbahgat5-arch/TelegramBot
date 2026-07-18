"""Telegram ``Bot`` factory (MASTER_PLAN Task 6.3 / 6.7, D-040).

Builds the aiogram ``Bot`` used by both the bot and worker composition roots. When
``BOT_API_BASE_URL`` is set, the client targets a self-hosted Telegram Bot API
server (2 GB upload cap); otherwise it uses the public api.telegram.org (50 MB).

The aiohttp session's per-request timeout is raised from aiogram's 60 s default to the
per-job budget (``WORKER_JOB_TIMEOUT``, 300 s by default). Uploading even a modest video
(e.g. ~20 MB on a slow uplink at a few hundred KB/s) can take well over a minute, so the
60 s default made ``send_video`` time out — a valid file failed to deliver, was counted as
a (retryable) upload error, and retried repeatedly, blocking the user. One timeout for the
whole job budget matches how long a download+upload is allowed to take.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import FilesPathWrapper, TelegramAPIServer

from core.config import Settings


class LocalBotApiPathWrapper(FilesPathWrapper):
    """Resolve the file paths our self-hosted Bot API returns, in ``--local`` mode.

    Measured against the running server (2026-07-18): it does **not** serve files over
    HTTP (``/file/bot<token>/…`` 404s), and ``getFile`` returns a path *relative to the
    per-bot directory* — e.g. ``documents/file_2.txt`` — rather than the absolute path
    aiogram's local mode expects. Left unresolved that becomes
    ``FileNotFoundError: 'documents/file_2.txt'``.

    aiogram's own ``SimpleFilesPathWrapper`` cannot express this: it calls
    ``Path.relative_to`` and so requires an already-absolute path. This wrapper simply
    anchors a relative path under ``<root>/<token>/`` and passes absolute paths through,
    which keeps it correct if a future server version starts returning absolute paths.
    """

    def __init__(self, root: Path | str, token: str) -> None:
        # PurePosixPath, not Path: these paths come from a Linux container and are
        # always POSIX. Using the host flavour would make "/var/lib/..." parse as a
        # *relative* path on Windows, so the logic would differ between a developer
        # machine and production — the kind of split that hides bugs until deploy.
        self._base = PurePosixPath(str(root)) / token

    def to_local(self, path: Path | str) -> Path | str:
        candidate = PurePosixPath(str(path))
        resolved = candidate if candidate.is_absolute() else self._base / candidate
        return str(resolved)  # str, not PurePosixPath: aiofiles.open takes either

    def to_server(self, path: Path | str) -> Path | str:
        candidate = PurePosixPath(str(path))
        if not candidate.is_absolute():
            return str(candidate)
        try:
            return str(candidate.relative_to(self._base))
        except ValueError:
            return str(candidate)


def build_bot(settings: Settings) -> Bot:
    timeout = float(settings.worker_job_timeout)
    if settings.use_local_bot_api:
        # ``is_local=True`` is required with a self-hosted server running in --local mode:
        # ``getFile`` there returns an absolute path on the SERVER's filesystem and the
        # file is never served over HTTP, so aiogram must read it from disk instead of
        # fetching a URL (which 404s). The bot container mounts the same
        # ``/var/lib/telegram-bot-api`` volume read-only so that path resolves.
        #
        # This only affects downloads — aiogram consults ``is_local`` in exactly one
        # place, ``Bot.download_file``. Uploads (send_video and friends) are unchanged,
        # so the worker's delivery path is unaffected.
        token = settings.bot_token.get_secret_value()
        api = TelegramAPIServer.from_base(settings.bot_api_base_url, is_local=True)
        # Rebuild with the path wrapper: from_base() has no parameter for it, and the
        # dataclass is frozen.
        api = TelegramAPIServer(
            base=api.base,
            file=api.file,
            is_local=True,
            wrap_local_file=LocalBotApiPathWrapper(settings.bot_api_local_root, token),
        )
        session = AiohttpSession(api=api, timeout=timeout)
    else:
        session = AiohttpSession(timeout=timeout)
    return Bot(
        token=settings.bot_token.get_secret_value(),
        session=session,
        default=DefaultBotProperties(parse_mode=settings.bot_parse_mode),
    )
