"""Guards on the deploy Dockerfiles (container / Railway readiness).

These are static invariants a container deploy relies on: the worker image must
ship the runtime binaries the download pipeline shells out to (ffmpeg + yt-dlp),
and yt-dlp must be pinned exactly (§6.4) like every other dependency.
"""

from __future__ import annotations

import re
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"


def _read(name: str) -> str:
    return (DEPLOY / name).read_text(encoding="utf-8")


def test_worker_image_installs_ffmpeg() -> None:
    # The transcoder shells out to ffmpeg (FFMPEG_PATH).
    assert "ffmpeg" in _read("Dockerfile.worker")


def test_worker_image_installs_pinned_ytdlp() -> None:
    # yt-dlp is invoked as a *binary subprocess* (YtDlpProvider wraps the `yt-dlp`
    # binary, no Python import), so the worker image must install it — otherwise
    # every download fails with "yt-dlp not found". Pinned exactly, date-versioned.
    dockerfile = _read("Dockerfile.worker")
    assert re.search(r"yt-dlp==\d{4}\.\d{1,2}\.\d{1,2}", dockerfile), (
        "Dockerfile.worker must install a pinned yt-dlp==<date> — the download "
        "pipeline shells out to the yt-dlp binary at runtime."
    )


def test_worker_and_bot_run_the_expected_entrypoints() -> None:
    assert "workers.main" in _read("Dockerfile.worker")
    assert "bot.main" in _read("Dockerfile.bot")
    assert "api.main" in _read("Dockerfile.api")


def test_builder_copies_source_before_installing() -> None:
    # The project declares explicit packages (api/bot/core/...), so `pip install .`
    # builds a wheel that needs the source in the build context. Guard against
    # regressing to a pyproject-only copy (which fails: "package directory 'api'
    # does not exist").
    for name in ("Dockerfile.api", "Dockerfile.bot", "Dockerfile.worker"):
        df = _read(name).replace("\r\n", "\n")
        copy_idx = df.find("COPY . .")
        install_idx = df.find("pip install --prefix=/install .")
        assert copy_idx != -1, f"{name}: builder must COPY the full source"
        assert install_idx != -1, f"{name}: builder must install into /install"
        assert copy_idx < install_idx, f"{name}: COPY source must precede the install"
