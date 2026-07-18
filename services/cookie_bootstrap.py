"""Bring the cookie pool up on process start (DESIGN_COOKIE_POOL.md §16).

Two jobs, both idempotent and both best-effort — a pool that cannot start must never
stop the bot from starting, because anonymous extraction still works:

1. **Import the legacy master.** A deployment upgrading from the single-file era has a
   populated ``cookies.txt`` and an empty pool. That file becomes ``yt-01`` so the
   migration is invisible: same cookie, same behaviour, now with health tracking.
2. **Reconcile.** A row whose file has vanished is marked INVALID rather than being
   handed out and failing every request.
"""

from __future__ import annotations

from pathlib import Path

from core.logging import get_logger
from domain.enums.cookie_health import CookieHealth
from domain.protocols.cookies import CookieRepositoryProtocol, CookieStoreProtocol
from services.cookie_validator import validate_cookie_file

_log = get_logger("services.cookie_bootstrap")

LEGACY_LABEL = "yt-01"


async def bootstrap_cookie_pool(
    repo: CookieRepositoryProtocol,
    store: CookieStoreProtocol,
    *,
    legacy_master: Path | str | None = None,
    default_egress_id: str | None = None,
) -> None:
    try:
        await _import_legacy(repo, store, legacy_master, default_egress_id)
        await _reconcile(repo, store)
    except Exception as exc:  # never block startup on the pool
        _log.warning("cookie_bootstrap_failed", error=str(exc))


async def _import_legacy(
    repo: CookieRepositoryProtocol,
    store: CookieStoreProtocol,
    legacy_master: Path | str | None,
    default_egress_id: str | None,
) -> None:
    if not legacy_master:
        return
    path = Path(legacy_master)
    if not path.exists() or path.stat().st_size == 0:
        return
    if await repo.list_all():
        return  # pool already populated — never re-import over a live pool

    content = path.read_bytes()
    check = validate_cookie_file(content)
    if not check.ok:
        _log.warning("cookie_legacy_import_rejected", reason=check.reason)
        return

    digest = await store.write(LEGACY_LABEL, 1, content)
    cookie = await repo.create(
        label=LEGACY_LABEL,
        file_version=1,
        content_hash=digest,
        created_by=None,
        egress_id=default_egress_id,
    )
    await repo.add_event(
        cookie.id,
        event="cookie_imported",
        to_status=CookieHealth.HEALTHY,
        reason="imported from the legacy single-cookie master",
        egress_id=default_egress_id,
    )
    _log.info(
        "cookie_legacy_imported",
        cookie_label=LEGACY_LABEL,
        cookies=check.cookie_count,
        egress_id=default_egress_id,
    )


async def _reconcile(repo: CookieRepositoryProtocol, store: CookieStoreProtocol) -> None:
    """Mark rows whose material is gone, so selection never hands out a dead path."""
    for cookie in await repo.list_all():
        if cookie.status is CookieHealth.INVALID:
            continue
        if await store.exists(cookie.label, cookie.file_version):
            continue
        await repo.set_status(
            cookie.id,
            status=CookieHealth.INVALID,
            reason=f"cookie file missing for {cookie.label} v{cookie.file_version}",
        )
        _log.warning(
            "cookie_file_missing", cookie_label=cookie.label, version=cookie.file_version
        )
