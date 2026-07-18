"""AdminNotificationService — pushes important events to the Owner + all Moderators.

Whenever a noteworthy event happens (a new user joins, a user blocks the bot, an
admin bans/unbans someone, a broadcast is published, …) every staff member is sent a
concise, localized notification with the relevant member info and running totals —
matching the Owner's requested format.

Delivery is **best-effort and never fails the caller**: the triggering action (the
user's ``/start``, the admin's ban) must succeed regardless of whether a notification
sends. Each recipient is messaged in *their own* locale (i18n parity), so an Arabic
admin sees Arabic and an English admin sees English. Every event is also written to the
structured log, so it is auditable on the server even if Telegram delivery fails.

Framework-agnostic: depends on ``MessageSenderProtocol`` (raw text transport) and the
user repository, both injected at the composition root.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from html import escape
from typing import Any

from core.i18n import resolve_locale, translate
from core.logging import get_logger
from domain.entities.user import UserSnapshot
from domain.protocols.file_sender import MessageSenderProtocol
from domain.protocols.repositories import UserRepositoryProtocol

_log = get_logger("services.admin_notification")

# Recipient-locale text builder: given a locale, produce the message body.
_Build = Callable[[str], str]


class AdminNotificationService:
    def __init__(
        self,
        sender: MessageSenderProtocol,
        users: UserRepositoryProtocol[Any],
        *,
        cookie_replace_cb: Callable[[int], str] | None = None,
    ) -> None:
        self._sender = sender
        self._users = users
        # Builds signed callback data for the cookie "Replace" button. Injected so this
        # service never imports the bot layer's callback signer.
        self._cookie_replace_cb = cookie_replace_cb

    # --- public event API --------------------------------------------------

    async def notify_new_user(self, user: UserSnapshot) -> None:
        """First-ever contact: a brand-new user joined the bot."""
        total = await self._users.count_all()
        _log.info("admin_event", kind="new_user", user_id=user.telegram_id, total_users=total)
        await self._fanout(
            "new_user",
            lambda loc: _compose(
                translate("adminnotify.new_user.title", loc),
                _member_block(user, loc, new=True),
                translate("adminnotify.total_users", loc, count=total),
            ),
        )

    async def notify_user_returned(self, user: UserSnapshot) -> None:
        """A previously-blocked user came back and is using the bot again."""
        total = await self._users.count_all()
        blocked = await self._users.count_blocked()
        _log.info("admin_event", kind="user_returned", user_id=user.telegram_id)
        await self._fanout(
            "user_returned",
            lambda loc: _compose(
                translate("adminnotify.returned.title", loc),
                _member_block(user, loc),
                translate("adminnotify.total_users", loc, count=total),
                translate("adminnotify.total_blocked", loc, count=blocked),
            ),
        )

    async def notify_bot_blocked(self, user: UserSnapshot) -> None:
        """A user blocked the bot."""
        blocked = await self._users.count_blocked()
        _log.info(
            "admin_event", kind="bot_blocked", user_id=user.telegram_id, total_blocked=blocked
        )
        await self._fanout(
            "bot_blocked",
            lambda loc: _compose(
                translate("adminnotify.blocked.title", loc),
                _member_block(user, loc),
                translate("adminnotify.total_blocked", loc, count=blocked),
            ),
        )

    async def notify_user_banned(
        self, target: UserSnapshot, *, by_admin: UserSnapshot | None, reason: str | None = None
    ) -> None:
        """An admin banned a user."""
        _log.info(
            "admin_event",
            kind="user_banned",
            target_id=target.telegram_id,
            by_admin=by_admin.telegram_id if by_admin else None,
            reason=reason,
        )
        await self._fanout(
            "user_banned",
            lambda loc: _compose(
                translate("adminnotify.banned.title", loc),
                _member_block(target, loc),
                _by_line(by_admin, loc),
                _reason_line(reason, loc),
            ),
        )

    async def notify_user_unbanned(
        self, target: UserSnapshot, *, by_admin: UserSnapshot | None
    ) -> None:
        """An admin unbanned a user."""
        _log.info(
            "admin_event",
            kind="user_unbanned",
            target_id=target.telegram_id,
            by_admin=by_admin.telegram_id if by_admin else None,
        )
        await self._fanout(
            "user_unbanned",
            lambda loc: _compose(
                translate("adminnotify.unbanned.title", loc),
                _member_block(target, loc),
                _by_line(by_admin, loc),
            ),
        )

    async def notify_broadcast_published(
        self, *, by_admin: UserSnapshot | None, broadcast_id: int, expected_total: int
    ) -> None:
        """An admin published a broadcast."""
        _log.info(
            "admin_event",
            kind="broadcast_published",
            broadcast_id=broadcast_id,
            expected_total=expected_total,
            by_admin=by_admin.telegram_id if by_admin else None,
        )
        await self._fanout(
            "broadcast_published",
            lambda loc: _compose(
                translate("adminnotify.broadcast.title", loc, id=broadcast_id),
                translate("adminnotify.broadcast.recipients", loc, count=expected_total),
                _by_line(by_admin, loc),
            ),
        )

    async def notify_ad_published(
        self, *, by_admin: UserSnapshot | None, ad_id: int, title: str | None = None
    ) -> None:
        """An admin published/activated an advertisement."""
        _log.info(
            "admin_event",
            kind="ad_published",
            ad_id=ad_id,
            by_admin=by_admin.telegram_id if by_admin else None,
        )
        await self._fanout(
            "ad_published",
            lambda loc: _compose(
                translate("adminnotify.ad.title", loc, id=ad_id),
                (f"• {escape(title)}" if title else None),
                _by_line(by_admin, loc),
            ),
        )

    # --- cookie pool (DESIGN_COOKIE_POOL.md §9) -----------------------------

    async def notify_cookie_unhealthy(
        self,
        *,
        label: str,
        status: str,
        reason: str,
        last_success_at: str | None,
        consecutive_failures: int,
        healthy: int,
        total: int,
        egress_id: str | None = None,
        cookie_id: int | None = None,
        by_admin: UserSnapshot | None = None,
    ) -> None:
        """A cookie reached a terminal state (expired / invalid / disabled).

        Fires on the *transition*, never per failure, so a degrading pool cannot turn
        into a stream of messages. The pool summary is what tells an admin whether to
        act now or after coffee.
        """
        _log.info(
            "admin_event",
            kind="cookie_unhealthy",
            cookie_label=label,
            status=status,
            healthy=healthy,
            total=total,
        )
        buttons = self._cookie_buttons(cookie_id)
        await self._fanout(
            "cookie_unhealthy",
            lambda loc: _compose(
                translate("adminnotify.cookie.title", loc, label=escape(label)),
                f"• {translate('adminnotify.cookie.status', loc)}: "
                f"<b>{escape(status.upper())}</b>",
                (
                    f"• {translate('adminnotify.cookie.reason', loc)}: {escape(reason)}"
                    if reason
                    else None
                ),
                f"• {translate('adminnotify.cookie.last_success', loc)}: "
                + (
                    escape(last_success_at)
                    if last_success_at
                    else translate("adminnotify.none", loc)
                ),
                f"• {translate('adminnotify.cookie.failures', loc)}: {consecutive_failures}",
                (
                    f"• {translate('adminnotify.cookie.egress', loc)}: {escape(egress_id)}"
                    if egress_id
                    else None
                ),
                f"• {translate('adminnotify.cookie.pool', loc, healthy=healthy, total=total)}",
                _by_line(by_admin, loc),
            ),
            buttons=lambda loc: (
                [(translate("adminnotify.cookie.btn_replace", loc), buttons)]
                if buttons
                else None
            ),
        )

    async def notify_cookie_recovered(
        self, *, label: str, healthy: int, total: int
    ) -> None:
        """A cookie came back to healthy — quiet by design, no action needed."""
        _log.info("admin_event", kind="cookie_recovered", cookie_label=label)
        await self._fanout(
            "cookie_recovered",
            lambda loc: _compose(
                translate("adminnotify.cookie.recovered", loc, label=escape(label)),
                f"• {translate('adminnotify.cookie.pool', loc, healthy=healthy, total=total)}",
            ),
        )

    def _cookie_buttons(self, cookie_id: int | None) -> str | None:
        """Signed callback data for the Replace action, or None when unavailable.

        The builder is injected from the composition root (it needs the callback
        signer), which keeps this service free of any bot-framework import.
        """
        if cookie_id is None or self._cookie_replace_cb is None:
            return None
        try:
            return self._cookie_replace_cb(cookie_id)
        except Exception as exc:  # a bad button must not cost the notification
            _log.warning("cookie_button_build_failed", error=str(exc))
            return None

    # --- delivery ----------------------------------------------------------

    async def _fanout(
        self,
        event: str,
        build: _Build,
        *,
        buttons: Callable[[str], list[tuple[str, str]] | None] | None = None,
    ) -> None:
        """Send ``build(locale)`` to every staff member, each in their own locale.

        Never raises: a failed staff lookup or a single failed send is logged and
        swallowed so the triggering action is unaffected.
        """
        try:
            staff = await self._users.list_staff()
        except Exception as exc:
            _log.warning("admin_notify_staff_lookup_failed", kind=event, error=str(exc))
            return
        for row in staff:
            locale = resolve_locale(getattr(row, "language", None))
            try:
                # These bodies contain HTML (<b>, <code>); request HTML explicitly —
                # the shared sender passes parse_mode through, and an unset value would
                # be sent as None, overriding the bot's HTML default (tags shown raw).
                markup = buttons(locale) if buttons else None
                extra = {"buttons": markup} if markup else {}
                await self._sender.send_message(
                    row.telegram_id, build(locale), parse_mode="HTML", **extra
                )
            except Exception as exc:
                _log.info(
                    "admin_notify_send_failed",
                    kind=event,
                    admin_id=getattr(row, "telegram_id", None),
                    error=str(exc),
                )


NotifyFn = Callable[[], Awaitable[None]]


def _compose(*parts: str | None) -> str:
    return "\n".join(p for p in parts if p)


def _member_block(user: UserSnapshot, locale: str, *, new: bool = False) -> str:
    """The ``👤 Member info`` block: name · username · id · language (user text escaped)."""
    header_key = "adminnotify.new_member_info" if new else "adminnotify.member_info"
    name = escape(user.first_name) if user.first_name else translate("adminnotify.unknown", locale)
    username = f"@{escape(user.username)}" if user.username else translate(
        "adminnotify.none", locale
    )
    language = escape(user.language) if user.language else "—"
    return _compose(
        translate(header_key, locale),
        f"• {translate('adminnotify.f.name', locale)}: {name}",
        f"• {translate('adminnotify.f.username', locale)}: {username}",
        f"• {translate('adminnotify.f.id', locale)}: <code>{user.telegram_id}</code>",
        f"• {translate('adminnotify.f.language', locale)}: {language}",
    )


def _by_line(by_admin: UserSnapshot | None, locale: str) -> str | None:
    if by_admin is None:
        return None
    who = escape(by_admin.first_name) if by_admin.first_name else str(by_admin.telegram_id)
    return translate("adminnotify.by", locale, name=who)


def _reason_line(reason: str | None, locale: str) -> str | None:
    if not reason:
        return None
    return translate("adminnotify.reason", locale, reason=escape(reason))
