"""Downloader provider protocol (MASTER_PLAN 12.6.2, Task 5.1, LOCKED).

The single interface the service layer depends on for all content extraction and
download. Concrete providers live in ``infrastructure/downloader/providers/`` and
are selected by ``DownloaderRegistry`` — no layer above infrastructure ever names a
provider (D-029, Section 12.6.9).

Co-located here (per Task 5.1) are the protocol's companion types: the
``Capability`` and ``ProviderHealth`` enums and the two control-flow exceptions the
registry interprets (``ProviderUnsupported``, ``ProviderRetryElsewhere``). They are
tightly bound to the protocol's contract; the broad domain exception hierarchy
(Section 15.4) is unchanged.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

from domain.entities.media import DownloadedFile, MediaInfo
from domain.enums import MediaFormat, Quality
from domain.exceptions import AppError

# Reports live download progress: (downloaded_bytes, total_bytes | None). ``total`` is
# None when the source does not report a size. Best-effort — never raises to the caller.
DownloadProgress = Callable[[int, int | None], Awaitable[None]]


class Capability(StrEnum):
    """What a provider can produce (MASTER_PLAN 12.6.2)."""

    VIDEO = "video"
    AUDIO = "audio"
    LIVE_STREAM = "live_stream"
    PLAYLIST = "playlist"
    IMAGE = "image"


class ProviderHealth(StrEnum):
    """A provider's current usability (MASTER_PLAN 12.6.4)."""

    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ProviderUnsupported(AppError):  # noqa: N818 - name fixed by MASTER_PLAN 12.6.8
    """A provider opts out of a request; the registry tries the next candidate.

    Not an error condition — control flow. The registry advances silently
    (Section 12.6.8: "URL valid but provider does not support this platform").
    """


class ProviderRetryElsewhere(AppError):  # noqa: N818 - name fixed by MASTER_PLAN 12.6.8
    """A provider hit a transient failure; the registry should try the next one.

    The registry marks the provider DEGRADED and advances (Section 12.6.8). If
    failover is disabled, it propagates.
    """


class ProviderSettingsProtocol(Protocol):
    """Runtime provider settings the registry reads (Section 12.6.7).

    Implemented by a thin adapter over ``SettingsService`` (services layer) and
    injected at the composition root — this keeps the registry (infrastructure)
    from importing services (Section 8).
    """

    async def providers_enabled(self) -> dict[str, bool]: ...
    async def priority_overrides(self) -> dict[str, int]: ...
    async def failover_enabled(self) -> bool: ...
    async def cooldown_seconds(self) -> int: ...
    async def failure_threshold(self) -> int: ...


@runtime_checkable
class DownloaderProtocol(Protocol):
    """Contract every download provider implements (MASTER_PLAN 12.6.2)."""

    name: str
    supported_platforms: set[str]
    capabilities: set[Capability]
    priority: int

    async def extract_info(self, url: str) -> MediaInfo:
        """Discover metadata + available formats for ``url``."""
        ...

    async def download(
        self,
        media: MediaInfo,
        format_: MediaFormat,
        quality: Quality,
        dest: Path,
        *,
        progress_cb: DownloadProgress | None = None,
    ) -> DownloadedFile:
        """Produce a local file for the chosen (format, quality) under ``dest``.

        ``progress_cb`` (optional) is invoked with live (downloaded, total) byte counts
        during the transfer so the caller can render a progress bar.
        """
        ...

    async def health_check(self) -> ProviderHealth:
        """Probe the provider's current health."""
        ...
