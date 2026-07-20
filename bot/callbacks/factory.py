"""Signed callback data (MASTER_PLAN Task 5.8, Section 14.2).

Inline-button callbacks carry ``(media_id, format[, quality])``. Each payload is
HMAC-signed so a tampered callback is rejected and silently ignored (never echoed).
The encoded form stays well within Telegram's 64-byte ``callback_data`` limit.

Seven actions:
* ``f`` — format chosen (``f|<media_id>|<format>|<sig>``) → show the quality keyboard.
* ``q`` — quality chosen (``q|<media_id>|<format>|<quality>|<sig>``) → start download.
* ``b`` — back (``b|<media_id>|<sig>``) → return to the format (Video/Audio) keyboard.
* ``g`` — gallery step (``g|<media_id>|<index>|<op>|<sig>``) → browse a multi-item post
  inside one message. ``op`` is n/v/a/q/i (navigate, video, audio, qualities, image);
  it rides in ``ParsedCallback.language``, which is the free-form string field.
* ``r`` — resend (``r|<download_id>|<sig>``) → re-send a history entry (flow 16.3).
* ``h`` — history page (``h|<page>|<sig>``) → paginate the history list.
* ``a`` — ad click (``a|<ad_id>|<sig>``) → record the click + deliver the link (16.7 W6).
* ``l`` — language chosen (``l|<code>|<sig>``) → persist the pick (Sprint 11.5). The
  handler still validates ``code`` against ``core.i18n.list_enabled_locales()`` before
  acting on it (a locale can be disabled between rendering the picker and the tap).

A seventh namespace, ``P``, carries the admin inline control panel (Sprint 9.6,
F-2 / EP-22). Its payload is a fixed five-field, signed form
``P|<section>|<action>|<arg>|<value>|<sig>`` where ``arg``/``value`` are optional
ints (empty when unused). ``section`` and ``action`` are opaque short codes — the
signer never enumerates them, so new panel sections (Analytics, Payments, …) need
no change here; the section *registry* lives in the keyboard layer. Tampered panel
data fails the signature check and is silently ignored (Section 14.2), and
:meth:`CallbackSigner.pack_panel` refuses to emit data over Telegram's 64-byte limit.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from domain.enums import MediaFormat, Quality

_SEP = "|"
_SIG_LEN = 10  # hex chars of the truncated HMAC — enough for this low-value token.
_PANEL = "P"  # admin-panel namespace prefix (Sprint 9.6); distinct from f/q/b/r/h/a.
_TELEGRAM_CALLBACK_LIMIT = 64  # bytes; Telegram rejects callback_data above this.


@dataclass(frozen=True, slots=True)
class ParsedCallback:
    action: str  # "f", "q", "b", "c", "r", "h", "a", or "l"
    media_id: int = 0  # the media id for f/q/b actions; 0 for r/h/a/l
    format: MediaFormat | None = None
    quality: Quality | None = None
    arg: int | None = None  # download_id "r"; page "h"; ad_id "a"; carousel index "c"
    button_id: int | None = None  # ad button id for "a" (None = legacy single button)
    language: str | None = None  # locale code for "l"
    origin: str | None = None  # where the language picker opened from ("s"/"p"), for #7


@dataclass(frozen=True, slots=True)
class ParsedPanel:
    """A verified admin-panel callback (Sprint 9.6 ``P`` namespace).

    ``section`` and ``action`` are the opaque short codes the keyboard registry
    assigned; ``arg`` is the primary int (entity id / list page / setting-key index)
    and ``value`` the secondary int (e.g. the stepper's candidate value). Both ints
    are ``None`` when the originating button did not carry them.
    """

    section: str
    action: str
    arg: int | None = None
    value: int | None = None


class CallbackSigner:
    """Packs and verifies signed inline-callback payloads."""

    def __init__(self, secret: str) -> None:
        self._key = secret.encode()

    def _sig(self, payload: str) -> str:
        return hmac.new(self._key, payload.encode(), hashlib.sha256).hexdigest()[:_SIG_LEN]

    def pack_format(self, media_id: int, format_: MediaFormat) -> str:
        payload = f"f{_SEP}{media_id}{_SEP}{format_.value}"
        return f"{payload}{_SEP}{self._sig(payload)}"

    def pack_quality(self, media_id: int, format_: MediaFormat, quality: Quality) -> str:
        payload = f"q{_SEP}{media_id}{_SEP}{format_.value}{_SEP}{quality.value}"
        return f"{payload}{_SEP}{self._sig(payload)}"

    def pack_gallery(self, media_id: int, index: int, op: str = "n") -> str:
        """Gallery step: ``g|<post media_id>|<1-based index>|<op>|<sig>``.

        One action with a sub-op keeps the whole browser inside a single namespace and
        well under Telegram's 64-byte limit. ``op``:
          ``n`` navigate to the item · ``v`` download video · ``a`` download audio
          ``q`` show available qualities · ``i`` download image
        ``media_id`` is the POST's row (the multi-item container), never an item's —
        an item only gets its own row once the user commits to downloading it.
        """
        payload = f"g{_SEP}{media_id}{_SEP}{index}{_SEP}{op}"
        return f"{payload}{_SEP}{self._sig(payload)}"

    def pack_back(self, media_id: int) -> str:
        payload = f"b{_SEP}{media_id}"
        return f"{payload}{_SEP}{self._sig(payload)}"

    def pack_resend(self, download_id: int) -> str:
        payload = f"r{_SEP}{download_id}"
        return f"{payload}{_SEP}{self._sig(payload)}"

    def pack_history_page(self, page: int) -> str:
        payload = f"h{_SEP}{page}"
        return f"{payload}{_SEP}{self._sig(payload)}"

    def pack_history_close(self) -> str:
        payload = f"hx{_SEP}0"
        return f"{payload}{_SEP}{self._sig(payload)}"

    def pack_language(self, code: str, origin: str = "") -> str:
        # ``origin`` (empty by default) records which screen opened the picker so the pick
        # can reopen it in the new locale (item #7); legacy 3-part callbacks stay valid.
        payload = f"l{_SEP}{code}{_SEP}{origin}" if origin else f"l{_SEP}{code}"
        return f"{payload}{_SEP}{self._sig(payload)}"

    def pack_referral(self) -> str:
        # "Try Premium / Referral" button on the Start menu (item #9) — renders the
        # caller's referral screen in place. The ``0`` keeps it at the 3-field minimum.
        payload = f"rf{_SEP}0"
        return f"{payload}{_SEP}{self._sig(payload)}"

    def pack_user_setting(self, arg: int) -> str:
        # User Settings screen (item #10): arg -1 opens the screen, -2 goes back to Start,
        # >=0 toggles SETTING_TOGGLES[arg]. Small signed int keeps callback_data tiny.
        payload = f"us{_SEP}{arg}"
        return f"{payload}{_SEP}{self._sig(payload)}"

    def pack_ad_click(self, ad_id: int, button_id: int | None = None) -> str:
        # 3-part (legacy single button) ``a|ad_id``; 4-part ``a|ad_id|button_id``.
        payload = f"a{_SEP}{ad_id}" if button_id is None else f"a{_SEP}{ad_id}{_SEP}{button_id}"
        return f"{payload}{_SEP}{self._sig(payload)}"

    def pack_panel(
        self, section: str, action: str, arg: int | None = None, value: int | None = None
    ) -> str:
        """Pack a signed admin-panel callback ``P|section|action|arg|value|sig``.

        ``section``/``action`` are caller-supplied short codes; empty optional ints
        render as empty fields. Raises ``ValueError`` if a code contains the field
        separator (would corrupt the encoding) or if the result would exceed
        Telegram's 64-byte ``callback_data`` limit — both are programmer errors that
        must surface at build time, not silently produce an unusable button.
        """
        if _SEP in section or _SEP in action:
            raise ValueError("panel section/action may not contain the field separator")
        arg_field = "" if arg is None else str(arg)
        value_field = "" if value is None else str(value)
        payload = f"{_PANEL}{_SEP}{section}{_SEP}{action}{_SEP}{arg_field}{_SEP}{value_field}"
        data = f"{payload}{_SEP}{self._sig(payload)}"
        if len(data.encode()) > _TELEGRAM_CALLBACK_LIMIT:
            raise ValueError(
                f"panel callback_data exceeds {_TELEGRAM_CALLBACK_LIMIT} bytes: {data!r}"
            )
        return data

    def unpack_panel(self, data: str) -> ParsedPanel | None:
        """Verify and parse a ``P`` panel callback. Returns None on any forged/malformed input."""
        parts = data.split(_SEP)
        if len(parts) != 6 or parts[0] != _PANEL:
            return None
        payload, sig = _SEP.join(parts[:-1]), parts[-1]
        if not hmac.compare_digest(sig, self._sig(payload)):
            return None
        section, action, arg_field, value_field = parts[1], parts[2], parts[3], parts[4]
        if not section or not action:
            return None
        try:
            arg = int(arg_field) if arg_field else None
            value = int(value_field) if value_field else None
        except ValueError:
            return None
        return ParsedPanel(section=section, action=action, arg=arg, value=value)

    def unpack(self, data: str) -> ParsedCallback | None:
        """Verify and parse callback data. Returns None on any malformed/forged input."""
        parts = data.split(_SEP)
        if len(parts) < 3:
            return None
        payload, sig = _SEP.join(parts[:-1]), parts[-1]
        if not hmac.compare_digest(sig, self._sig(payload)):
            return None
        try:
            action = parts[0]
            if action == "r" and len(parts) == 3:
                return ParsedCallback(action="r", arg=int(parts[1]))
            if action == "h" and len(parts) == 3:
                return ParsedCallback(action="h", arg=int(parts[1]))
            if action == "hx" and len(parts) == 3:
                return ParsedCallback(action="hx", arg=int(parts[1]))
            if action == "l" and len(parts) == 4:
                return ParsedCallback(action="l", language=parts[1], origin=parts[2] or None)
            if action == "l" and len(parts) == 3:
                return ParsedCallback(action="l", language=parts[1])
            if action == "us" and len(parts) == 3:
                return ParsedCallback(action="us", arg=int(parts[1]))
            if action == "rf" and len(parts) == 3:
                return ParsedCallback(action="rf")
            if action == "a" and len(parts) == 3:
                return ParsedCallback(action="a", arg=int(parts[1]))
            if action == "a" and len(parts) == 4:
                return ParsedCallback(action="a", arg=int(parts[1]), button_id=int(parts[2]))
            media_id = int(parts[1])
            if action == "g" and len(parts) == 5:
                return ParsedCallback(
                    action="g", media_id=media_id, arg=int(parts[2]), language=parts[3]
                )
            if action == "b" and len(parts) == 3:
                return ParsedCallback(action="b", media_id=media_id)
            if action == "f" and len(parts) == 4:
                return ParsedCallback(action="f", media_id=media_id, format=MediaFormat(parts[2]))
            if action == "q" and len(parts) == 5:
                return ParsedCallback(
                    action="q",
                    media_id=media_id,
                    format=MediaFormat(parts[2]),
                    quality=Quality(parts[3]),
                )
        except (ValueError, KeyError):
            return None
        return None
