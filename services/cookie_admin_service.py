"""CookieAdminService — the safe path for adding/replacing a cookie (§10).

Every ingest goes through the same four gates, in this order:

1. **Validate** — cheap, catches "pasted the wrong export" in milliseconds.
2. **Canary** — one real extraction with the candidate file. This is what turns
   "I hope that worked" into a verified state change; without it a dead session
   silently occupies a pool slot until downloads start failing.
3. **Compare-and-swap** on ``file_version`` — rejects the upload if someone else
   replaced the same cookie while this one was in flight.
4. **Commit** — new version file, health reset, audit event.

A failure at any gate leaves the existing cookie completely untouched.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.logging import get_logger
from domain.entities.cookie import CookieEvent, CookieSnapshot
from domain.enums.cookie_health import SELECTABLE_HEALTH, CookieHealth
from domain.protocols.cookies import (
    CookieCanaryProtocol,
    CookieRepositoryProtocol,
    CookieStoreProtocol,
)
from services.cookie_validator import validate_cookie_file

_log = get_logger("services.cookie_admin")


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Outcome of an add/replace attempt, ready to render to the admin."""

    ok: bool
    kind: str  # "replaced" | "added" | "invalid" | "canary_failed" | "conflict" | "error"
    detail: str = ""
    label: str = ""
    version: int = 0


class CookieAdminService:
    def __init__(
        self,
        repo: CookieRepositoryProtocol,
        store: CookieStoreProtocol,
        canary: CookieCanaryProtocol,
    ) -> None:
        self._repo = repo
        self._store = store
        self._canary = canary

    async def list_pool(self) -> list[CookieSnapshot]:
        """Every cookie, for the admin panel's list and statistics screens."""
        return await self._repo.list_all()

    async def get(self, cookie_id: int) -> CookieSnapshot | None:
        return await self._repo.get(cookie_id)

    async def history(self, cookie_id: int, *, limit: int = 15) -> list[CookieEvent]:
        """Recent audit events for one cookie (newest first), for the panel."""
        lister = getattr(self._repo, "list_events", None)
        if lister is None:  # protocol keeps this optional; fakes need not implement it
            return []
        return list(await lister(cookie_id, limit=limit))

    async def pool_summary(self) -> tuple[int, int]:
        """``(healthy, total)`` — the line every notification carries."""
        cookies = await self._repo.list_all()
        healthy = sum(1 for c in cookies if c.status in SELECTABLE_HEALTH)
        return healthy, len(cookies)

    async def replace(
        self, cookie_id: int, content: bytes, *, actor_user_id: int | None = None
    ) -> IngestResult:
        """Replace one cookie's material. Only that cookie is touched."""
        cookie = await self._repo.get(cookie_id)
        if cookie is None:
            return IngestResult(False, "error", "cookie not found")

        gate = await self._gate(content, egress_id=cookie.egress_id)
        if not gate.ok:
            return gate

        new_version = cookie.file_version + 1
        digest = await self._store.write(cookie.label, new_version, content)
        swapped = await self._repo.replace_file(
            cookie.id,
            expected_version=cookie.file_version,
            new_version=new_version,
            content_hash=digest,
            actor_user_id=actor_user_id,
        )
        if not swapped:
            # Someone replaced it first: bin the file we just wrote rather than leaving
            # an orphan version, and tell the admin instead of clobbering their upload.
            await self._store.delete(cookie.label, new_version)
            _log.warning("cookie_replace_conflict", cookie_label=cookie.label)
            return IngestResult(False, "conflict", label=cookie.label)

        await self._store.prune(cookie.label, keep_from_version=new_version)
        _log.info(
            "cookie_replaced",
            cookie_label=cookie.label,
            version=new_version,
            actor=actor_user_id,
            canary=gate.detail,
        )
        return IngestResult(True, "replaced", gate.detail, cookie.label, new_version)

    async def add(
        self, content: bytes, *, label: str | None = None, actor_user_id: int | None = None
    ) -> IngestResult:
        """Add a new cookie to the pool. Label is auto-assigned when not given."""
        gate = await self._gate(content, egress_id=None)
        if not gate.ok:
            return gate

        chosen = label or await self._next_label()
        if await self._repo.get_by_label(chosen) is not None:
            return IngestResult(False, "error", f"label {chosen} already exists")

        digest = await self._store.write(chosen, 1, content)
        try:
            cookie = await self._repo.create(
                label=chosen, file_version=1, content_hash=digest, created_by=actor_user_id
            )
        except Exception:
            # The row is the source of truth; a file with no row is invisible to the
            # pool and would linger forever. (A real FK violation on the first live
            # upload left exactly such an orphan.)
            await self._store.delete(chosen, 1)
            _log.warning("cookie_add_rolled_back", cookie_label=chosen)
            raise
        await self._repo.add_event(
            cookie.id,
            event="cookie_added",
            to_status=CookieHealth.HEALTHY,
            reason=gate.detail,
            actor_user_id=actor_user_id,
        )
        _log.info("cookie_added", cookie_label=chosen, actor=actor_user_id)
        return IngestResult(True, "added", gate.detail, chosen, 1)

    async def test(self, cookie_id: int) -> IngestResult:
        """Run the canary against a live pool cookie ("Test now")."""
        cookie = await self._repo.get(cookie_id)
        if cookie is None:
            return IngestResult(False, "error", "cookie not found")
        path = await self._store.materialise(cookie.label, cookie.file_version)
        ok, detail = await self._canary.canary_check(
            cookie_path=path, egress_id=cookie.egress_id
        )
        _log.info(
            "cookie_tested", cookie_label=cookie.label, ok=ok, detail=detail[:120]
        )
        return IngestResult(ok, "tested", detail, cookie.label, cookie.file_version)

    async def set_enabled(
        self, cookie_id: int, *, enabled: bool, actor_user_id: int | None = None
    ) -> CookieSnapshot | None:
        """Disable takes a cookie out of rotation; enable returns it as HEALTHY."""
        cookie = await self._repo.get(cookie_id)
        if cookie is None:
            return None
        target = CookieHealth.HEALTHY if enabled else CookieHealth.DISABLED
        await self._repo.set_status(
            cookie.id,
            status=target,
            actor_user_id=actor_user_id,
            reason="enabled by admin" if enabled else "disabled by admin",
        )
        _log.info(
            "cookie_enabled" if enabled else "cookie_disabled",
            cookie_label=cookie.label,
            actor=actor_user_id,
        )
        return await self._repo.get(cookie_id)

    # ------------------------------------------------------------------ gates ---

    async def _gate(self, content: bytes, *, egress_id: str | None) -> IngestResult:
        """Validate then canary. Returns ``ok=True`` with the canary detail on success."""
        check = validate_cookie_file(content)
        if not check.ok:
            return IngestResult(False, "invalid", check.reason)

        # The candidate is written to a scratch version so the canary exercises the real
        # file path (and the wrapper's own handling) without touching any live cookie.
        scratch_label = "_candidate"
        digest_version = 0
        await self._store.write(scratch_label, digest_version, content)
        try:
            path = await self._store.materialise(scratch_label, digest_version)
            ok, detail = await self._canary.canary_check(
                cookie_path=path, egress_id=egress_id
            )
        finally:
            await self._store.delete(scratch_label, digest_version)

        if not ok:
            return IngestResult(False, "canary_failed", detail)
        return IngestResult(True, "gate_passed", detail)

    async def _next_label(self) -> str:
        existing = {c.label for c in await self._repo.list_all()}
        for index in range(1, 100):
            candidate = f"yt-{index:02d}"
            if candidate not in existing:
                return candidate
        return "yt-99"
