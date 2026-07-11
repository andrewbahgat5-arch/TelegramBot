"""Live download progress: yt-dlp progress-line parsing + bar rendering."""

from __future__ import annotations

import pytest

from infrastructure.downloader.providers.ytdlp_provider import _parse_progress
from services.download_service import (
    _human_size,
    _render_processing,
    _render_progress,
    _render_uploading,
)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("DLP 1024 24122115 NA", (1024, 24122115)),
        ("DLP 500 NA 2048", (500, 2048)),  # total unknown → falls back to the estimate
        ("DLP 500 NA NA", (500, None)),  # neither known
        ("[download]  44% of 28MiB", None),  # not a DLP line
        ("DLP NA 10 10", None),  # unparseable downloaded
        ("", None),
    ],
)
def test_parse_progress(line: str, expected: tuple[int, int | None] | None) -> None:
    assert _parse_progress(line) == expected


def test_render_progress_has_bar_percent_and_sizes() -> None:
    text = _render_progress(12_300_000, 28_000_000)  # 43.9% (binary MB)
    assert "43%" in text
    assert "▰" in text and "▱" in text
    # 10-block bar, monotonic fill.
    bar = text.split()[1]
    assert len(bar) == 10
    assert bar.count("▰") == 4  # round(0.439 * 10)
    assert "MB /" in text


def test_render_progress_unknown_total_shows_downloaded_only() -> None:
    text = _render_progress(5_000_000, None)
    assert "▰" not in text
    assert "4.8 MB" in text


def test_render_progress_caps_at_100() -> None:
    text = _render_progress(30_000_000, 28_000_000)  # over-report → clamp
    assert "100%" in text
    assert text.split()[1].count("▰") == 10


def test_human_size_units() -> None:
    assert _human_size(500) == "0 KB"
    assert _human_size(1_500_000) == "1.4 MB"
    assert _human_size(2_500_000_000) == "2.33 GB"


def test_render_uploading_shows_real_size_and_full_bar() -> None:
    # The post-download frame: a full bar, the *real* file size, and an upload notice —
    # it replaces the stale download bar (which showed one stream's partial size).
    text = _render_uploading(3_000_000, "en")
    assert "⬆️" in text  # distinct from the ⬇️ download bar
    assert "100%" in text
    assert text.count("▰") == 10 and "▱" not in text
    assert "2.9 MB" in text  # 3_000_000 bytes rendered as the real merged size


def test_render_processing_is_nonempty() -> None:
    assert _render_processing("en")
