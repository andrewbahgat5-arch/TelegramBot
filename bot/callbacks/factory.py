"""Signed callback data (MASTER_PLAN Task 5.8, Section 14.2).

Inline-button callbacks carry ``(media_id, format[, quality])``. Each payload is
HMAC-signed so a tampered callback is rejected and silently ignored (never echoed).
The encoded form stays well within Telegram's 64-byte ``callback_data`` limit.

Three actions:
* ``f`` — format chosen (``f|<media_id>|<format>|<sig>``) → show the quality keyboard.
* ``q`` — quality chosen (``q|<media_id>|<format>|<quality>|<sig>``) → start download.
* ``b`` — back (``b|<media_id>|<sig>``) → return to the format (Video/Audio) keyboard.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from domain.enums import MediaFormat, Quality

_SEP = "|"
_SIG_LEN = 10  # hex chars of the truncated HMAC — enough for this low-value token.


@dataclass(frozen=True, slots=True)
class ParsedCallback:
    action: str  # "f", "q", or "b"
    media_id: int
    format: MediaFormat | None = None
    quality: Quality | None = None


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

    def pack_back(self, media_id: int) -> str:
        payload = f"b{_SEP}{media_id}"
        return f"{payload}{_SEP}{self._sig(payload)}"

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
            media_id = int(parts[1])
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
