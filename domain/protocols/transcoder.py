"""Transcoder protocol (MASTER_PLAN Task 6.1, Component 9.5).

The single interface the download pipeline depends on for media transcoding. The
concrete implementation wraps FFmpeg (``infrastructure/downloader/ffmpeg_client.py``)
— no service ever subprocesses FFmpeg directly (Section 7.1, 1.3 rule 9). V1 uses it
to produce explicit per-codec audio outputs (D-041); video is delivered as the
provider merged it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from domain.entities.media import AudioTarget


class TranscoderProtocol(Protocol):
    async def transcode_audio(self, source: Path, target: AudioTarget) -> Path:
        """Produce an audio file in ``target``'s codec/container next to ``source``.

        Returns the path to the produced file. Raises ``FFmpegProcessingError`` on
        failure. Implementations may remux (``-c:a copy``) when the source codec is
        already one of ``target.native_acodecs``.
        """
        ...
