"""Security · Input Validation (MASTER_PLAN §25.9.1).

Malformed URLs, oversized/invalid callbacks, and forged callback data must be
rejected at the boundary — never trusted, never echoed.
"""

from __future__ import annotations

import pytest

from bot.callbacks.factory import CallbackSigner
from core.urls import is_valid_url
from domain.enums import MediaFormat, Quality

_SECRET = "unit-test-callback-secret"


def _signer() -> CallbackSigner:
    return CallbackSigner(_SECRET)


# --- Malformed URLs -------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "not-a-url",
        "ftp://example.com/file",  # wrong scheme
        "javascript:alert(1)",  # injection-style scheme
        "http://",  # no host
        "https:///path",  # no host
    ],
)
def test_malformed_urls_rejected(url: str) -> None:
    assert is_valid_url(url) is False


@pytest.mark.parametrize(
    "url",
    ["https://youtube.com/watch?v=abcdef", "http://example.com/a", "https://x.com/u/status/1"],
)
def test_well_formed_urls_accepted(url: str) -> None:
    assert is_valid_url(url) is True


def test_oversized_url_does_not_crash_validator() -> None:
    # An attacker-sized payload must be handled, not raise.
    huge = "https://example.com/" + ("a" * 100_000)
    assert is_valid_url(huge) is True
    assert is_valid_url("x" * 100_000) is False


# --- Invalid / forged callback data ---------------------------------------
def test_callback_with_tampered_signature_rejected() -> None:
    signer = _signer()
    good = signer.pack_format(123, MediaFormat.VIDEO)
    tampered = good[:-1] + ("0" if good[-1] != "0" else "1")
    assert signer.unpack(tampered) is None


def test_callback_with_swapped_payload_rejected() -> None:
    # Keep a valid signature but change the media id → signature no longer matches.
    signer = _signer()
    good = signer.pack_format(123, MediaFormat.VIDEO)
    parts = good.split("|")
    parts[1] = "999"
    assert signer.unpack("|".join(parts)) is None


def test_callback_too_few_parts_rejected() -> None:
    assert _signer().unpack("f|123") is None


def test_callback_non_numeric_id_rejected() -> None:
    signer = _signer()
    # Sign a structurally valid but non-numeric resend id.
    payload = "r|notanint"
    forged = f"{payload}|{signer._sig(payload)}"  # valid signature, non-numeric id
    assert signer.unpack(forged) is None


def test_quality_callback_roundtrips() -> None:
    signer = _signer()
    packed = signer.pack_quality(7, MediaFormat.VIDEO, Quality.P720)
    parsed = signer.unpack(packed)
    assert parsed is not None
    assert parsed.action == "q"
    assert parsed.media_id == 7
    assert parsed.format is MediaFormat.VIDEO
    assert parsed.quality is Quality.P720


# --- Oversized callbacks (Telegram 64-byte limit) -------------------------
def test_oversized_panel_callback_rejected_at_build_time() -> None:
    signer = _signer()
    with pytest.raises(ValueError, match="64 bytes"):
        signer.pack_panel("section", "action", arg=10**18, value=10**18)


def test_panel_separator_injection_rejected() -> None:
    signer = _signer()
    with pytest.raises(ValueError, match="separator"):
        signer.pack_panel("se|ction", "action")
