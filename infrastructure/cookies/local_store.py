"""LocalCookieStore — versioned cookie files on the local filesystem.

The only :class:`~domain.protocols.cookies.CookieStoreProtocol` implementation today.
Everything above it addresses cookies by ``(label, version)``, so replacing this with a
shared/object-storage implementation is what unlocks multi-server without touching
selection, health or the admin flow (DESIGN_COOKIE_POOL.md §14).

Layout::

    cookies.d/
        yt-01.v3.txt      <- live (version comes from the DB row)
        yt-01.v2.txt      <- previous, kept for rollback
        yt-03.v1.txt

Files are written with mode 0600 and never logged. The pool directory is git-ignored;
cookie material must never reach the repository.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from pathlib import Path

from core.logging import get_logger

_log = get_logger("infrastructure.cookies.local_store")

#: Labels become filenames, so they are restricted to a safe alphabet. This is the only
#: place a label reaches the filesystem — anything else would be a path-traversal risk.
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9._-]{1,40}$")


class InvalidCookieLabelError(ValueError):
    """A label that cannot be turned into a filename safely."""


class LocalCookieStore:
    def __init__(self, directory: Path | str) -> None:
        self._dir = Path(directory)

    async def _ensure_dir(self) -> None:
        await asyncio.to_thread(self._dir.mkdir, parents=True, exist_ok=True)

    def _path(self, label: str, version: int) -> Path:
        if not _SAFE_LABEL.match(label):
            raise InvalidCookieLabelError(f"unsafe cookie label: {label!r}")
        return self._dir / f"{label}.v{version}.txt"

    async def read(self, label: str, version: int) -> bytes:
        return await asyncio.to_thread(self._path(label, version).read_bytes)

    async def write(self, label: str, version: int, content: bytes) -> str:
        """Persist a version and return its sha256. Written 0600, owner-only."""
        await self._ensure_dir()
        path = self._path(label, version)

        def _write() -> None:
            # Write to a temp file in the same directory, then rename: a reader can never
            # observe a half-written jar. (Unlike the bind-mounted master file, these are
            # ordinary files, so an atomic rename is available here.)
            tmp = path.with_suffix(f".tmp{os.getpid()}")
            tmp.write_bytes(content)
            os.chmod(tmp, 0o600)
            tmp.replace(path)

        await asyncio.to_thread(_write)
        digest = hashlib.sha256(content).hexdigest()
        _log.info(
            "cookie_file_written", label=label, version=version, bytes=len(content)
        )
        return digest

    async def materialise(self, label: str, version: int) -> Path:
        """The local path yt-dlp should read. Already local — nothing to fetch."""
        path = self._path(label, version)
        if not await asyncio.to_thread(path.exists):
            raise FileNotFoundError(f"cookie file missing: {path}")
        return path

    async def delete(self, label: str, version: int) -> None:
        await asyncio.to_thread(self._path(label, version).unlink, True)

    async def exists(self, label: str, version: int) -> bool:
        return await asyncio.to_thread(self._path(label, version).exists)

    async def prune(self, label: str, *, keep_from_version: int, keep: int = 2) -> None:
        """Drop old versions, retaining the newest ``keep`` for rollback."""

        def _prune() -> None:
            versions: list[int] = []
            for candidate in self._dir.glob(f"{label}.v*.txt"):
                match = re.search(r"\.v(\d+)\.txt$", candidate.name)
                if match:
                    versions.append(int(match.group(1)))
            for version in sorted(versions, reverse=True)[keep:]:
                if version != keep_from_version:
                    self._dir.joinpath(f"{label}.v{version}.txt").unlink(missing_ok=True)

        await asyncio.to_thread(_prune)
