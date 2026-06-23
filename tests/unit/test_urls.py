"""Unit tests for core.urls (MASTER_PLAN 16.1, 12.6.3)."""

from __future__ import annotations

import pytest

from core.urls import detect_platform, extract_video_id, is_valid_url, normalize_url


@pytest.mark.parametrize(
    ("url", "valid"),
    [
        ("https://youtube.com/watch?v=abc", True),
        ("http://example.com/x", True),
        ("ftp://example.com", False),
        ("not a url", False),
        ("https://", False),
    ],
)
def test_is_valid_url(url: str, valid: bool) -> None:
    assert is_valid_url(url) is valid


def test_normalize_strips_fragment_and_lowercases_host() -> None:
    assert normalize_url("  HTTPS://YouTube.com/watch?v=A#frag ") == (
        "https://youtube.com/watch?v=A"
    )


@pytest.mark.parametrize(
    ("url", "platform"),
    [
        ("https://www.youtube.com/watch?v=dQw4", "youtube"),
        ("https://youtu.be/dQw4", "youtube"),
        ("https://www.tiktok.com/@u/video/123", "tiktok"),
        ("https://instagram.com/reel/AbC", "instagram"),
        ("https://x.com/u/status/9", "twitter"),
        ("https://example.org/clip", "generic"),
    ],
)
def test_detect_platform(url: str, platform: str) -> None:
    assert detect_platform(url) == platform


@pytest.mark.parametrize(
    ("url", "platform", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtube", "dQw4w9WgXcQ"),
        ("https://www.tiktok.com/@u/video/7212345678", "tiktok", "7212345678"),
        ("https://instagram.com/reel/AbC123", "instagram", "AbC123"),
        ("https://x.com/u/status/1554", "twitter", "1554"),
    ],
)
def test_extract_video_id_known_platforms(url: str, platform: str, expected: str) -> None:
    assert extract_video_id(url, platform) == expected


def test_extract_video_id_generic_is_stable_hash() -> None:
    url = "https://example.org/some/clip"
    first = extract_video_id(url, "generic")
    second = extract_video_id(url + "#x", "generic")  # fragment dropped by normalize
    assert first == second
    assert len(first) == 40  # sha1 hex
