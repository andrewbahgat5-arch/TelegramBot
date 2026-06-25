"""Unit tests for the signed callback factory (MASTER_PLAN Task 5.8, 14.2)."""

from __future__ import annotations

from bot.callbacks.factory import CallbackSigner
from domain.enums import MediaFormat, Quality


def _signer() -> CallbackSigner:
    return CallbackSigner("a-test-secret")


def test_format_round_trip() -> None:
    signer = _signer()
    data = signer.pack_format(42, MediaFormat.VIDEO)
    parsed = signer.unpack(data)
    assert parsed is not None
    assert parsed.action == "f"
    assert parsed.media_id == 42
    assert parsed.format is MediaFormat.VIDEO
    assert parsed.quality is None


def test_quality_round_trip() -> None:
    signer = _signer()
    parsed = signer.unpack(signer.pack_quality(7, MediaFormat.AUDIO, Quality.AUDIO))
    assert parsed is not None
    assert parsed.action == "q"
    assert parsed.media_id == 7
    assert parsed.quality is Quality.AUDIO


def test_back_round_trip() -> None:
    signer = _signer()
    parsed = signer.unpack(signer.pack_back(123))
    assert parsed is not None
    assert parsed.action == "b"
    assert parsed.media_id == 123
    assert parsed.format is None and parsed.quality is None


def test_back_tampered_rejected() -> None:
    signer = _signer()
    data = signer.pack_back(123)
    assert signer.unpack(data.replace("123", "124", 1)) is None


def test_resend_round_trip() -> None:
    signer = _signer()
    parsed = signer.unpack(signer.pack_resend(987))
    assert parsed is not None
    assert parsed.action == "r"
    assert parsed.arg == 987
    assert parsed.format is None and parsed.quality is None


def test_history_page_round_trip() -> None:
    signer = _signer()
    parsed = signer.unpack(signer.pack_history_page(3))
    assert parsed is not None
    assert parsed.action == "h"
    assert parsed.arg == 3


def test_resend_tampered_rejected() -> None:
    signer = _signer()
    data = signer.pack_resend(987)
    assert signer.unpack(data.replace("987", "988", 1)) is None


def test_ad_click_round_trip() -> None:
    signer = _signer()
    parsed = signer.unpack(signer.pack_ad_click(42))
    assert parsed is not None
    assert parsed.action == "a"
    assert parsed.arg == 42


def test_ad_click_tampered_rejected() -> None:
    signer = _signer()
    data = signer.pack_ad_click(42)
    assert signer.unpack(data.replace("42", "43", 1)) is None


def test_within_telegram_64_byte_limit() -> None:
    data = _signer().pack_quality(9_999_999_999, MediaFormat.VIDEO, Quality.P2160)
    assert len(data.encode()) <= 64


def test_tampered_payload_rejected() -> None:
    signer = _signer()
    data = signer.pack_format(42, MediaFormat.VIDEO)
    tampered = data.replace("42", "43", 1)
    assert signer.unpack(tampered) is None


def test_wrong_key_rejected() -> None:
    data = CallbackSigner("key-one").pack_format(1, MediaFormat.VIDEO)
    assert CallbackSigner("key-two").unpack(data) is None


def test_malformed_inputs_return_none() -> None:
    signer = _signer()
    assert signer.unpack("") is None
    assert signer.unpack("garbage") is None
    assert signer.unpack("f|notanint|video|deadbeef00") is None
