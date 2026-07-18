"""Cookie pool protocols (DESIGN_COOKIE_POOL.md §3, §14).

The seams that keep the layering intact:

* :class:`CookieProviderProtocol` is what the **downloader** depends on. ``YtdlpProvider``
  lives in ``infrastructure`` and must not import a service, so the concrete
  ``CookiePoolService`` is injected at the composition root — exactly as ``proxy`` and
  ``warp_proxy`` already are.
* :class:`CookieStoreProtocol` is where cookie *material* lives. The local-disk
  implementation is the only one today; a shared/object-storage implementation is what
  makes multi-server possible without touching selection logic (§14).
* :class:`CookieRepositoryProtocol` is metadata persistence.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from domain.entities.cookie import CookieLease, CookieSnapshot, CookieVerdict
from domain.enums.cookie_health import CookieHealth


@runtime_checkable
class CookieProviderProtocol(Protocol):
    """What the download provider needs: get a cookie, say how it went, give it back."""

    async def acquire(self, *, platform: str, egress_id: str) -> CookieLease | None:
        """Lease a cookie for ``platform`` on ``egress_id``, or None to run anonymously.

        None is a normal outcome, not an error: an empty/exhausted pool must degrade to
        anonymous extraction rather than failing the request (§15).
        """
        ...

    async def report(self, lease: CookieLease, verdict: CookieVerdict) -> None:
        """Record the outcome. Only ``verdict.affects_health`` changes health."""
        ...

    async def release(self, lease: CookieLease) -> None:
        """Release the lease. Must be safe to call twice and never raise."""
        ...


@runtime_checkable
class CookieStoreProtocol(Protocol):
    """Storage for cookie material, addressed by ``(label, version)``."""

    async def read(self, label: str, version: int) -> bytes: ...

    async def write(self, label: str, version: int, content: bytes) -> str:
        """Persist a version and return its content hash."""
        ...

    async def materialise(self, label: str, version: int) -> Path:
        """A local filesystem path yt-dlp can read. May be a cache on a shared store."""
        ...

    async def delete(self, label: str, version: int) -> None: ...

    async def exists(self, label: str, version: int) -> bool: ...


@runtime_checkable
class CookieRepositoryProtocol(Protocol):
    """Metadata, health and statistics persistence."""

    async def list_all(self) -> list[CookieSnapshot]: ...

    async def get(self, cookie_id: int) -> CookieSnapshot | None: ...

    async def get_by_label(self, label: str) -> CookieSnapshot | None: ...

    async def list_candidates(self, *, egress_id: str, now: datetime.datetime) -> list[
        CookieSnapshot
    ]:
        """Selectable cookies for an egress: affine first, then unpinned (§8)."""
        ...

    async def create(
        self, *, label: str, file_version: int, content_hash: str, created_by: int | None
    ) -> CookieSnapshot: ...

    async def record_use(self, cookie_id: int, *, at: datetime.datetime) -> None: ...

    async def record_outcome(
        self,
        cookie_id: int,
        *,
        verdict: CookieVerdict,
        status: CookieHealth,
        cooldown_until: datetime.datetime | None,
        auth_failures: int,
        cooldown_cycles: int,
        at: datetime.datetime,
    ) -> None: ...

    async def set_status(
        self,
        cookie_id: int,
        *,
        status: CookieHealth,
        actor_user_id: int | None = None,
        reason: str = "",
    ) -> None: ...

    async def set_egress(self, cookie_id: int, egress_id: str) -> None: ...

    async def replace_file(
        self,
        cookie_id: int,
        *,
        expected_version: int,
        new_version: int,
        content_hash: str,
        actor_user_id: int | None,
    ) -> bool:
        """Compare-and-swap on ``file_version``; False if someone replaced it first."""
        ...

    async def add_event(
        self,
        cookie_id: int,
        *,
        event: str,
        from_status: CookieHealth | None = None,
        to_status: CookieHealth | None = None,
        reason: str = "",
        egress_id: str | None = None,
        actor_user_id: int | None = None,
    ) -> None: ...
