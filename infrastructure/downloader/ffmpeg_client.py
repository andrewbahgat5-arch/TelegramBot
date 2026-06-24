"""FFmpegClient — the V1 transcoder (MASTER_PLAN Task 6.2, Section 7.1).

Wraps the ``ffmpeg`` binary as an async subprocess. This is the only module
permitted to subprocess FFmpeg (Section 1.3 rule 9); services depend on
``TranscoderProtocol``. V1 uses it to produce explicit per-codec audio outputs
(D-041): the source codec is remuxed (``-c:a copy``) when it already matches the
target container, otherwise it is re-encoded with the target's FFmpeg encoder.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from core.logging import get_logger
from domain.entities.media import AudioTarget
from domain.exceptions import FFmpegProcessingError

_log = get_logger("infrastructure.downloader.ffmpeg")

_DEFAULT_TRANSCODE_TIMEOUT = 300.0


class FFmpegClient:
    def __init__(
        self, ffmpeg_path: str = "ffmpeg", *, transcode_timeout: float = _DEFAULT_TRANSCODE_TIMEOUT
    ) -> None:
        self._bin = ffmpeg_path
        self._timeout = transcode_timeout

    async def transcode_audio(self, source: Path, target: AudioTarget) -> Path:
        """Produce ``source`` re-encoded (or remuxed) into ``target``'s codec/container."""
        dest = source.with_suffix(f".{target.container}")
        if dest == source:  # never overwrite the input in place
            dest = source.with_name(f"{source.stem}.out.{target.container}")
        codec_args = self._audio_codec_args(source, target)
        args = [
            self._bin,
            "-y",
            "-i",
            str(source),
            "-vn",  # drop any video stream — audio output only
            *codec_args,
            str(dest),
        ]
        await self._run(args)
        if not dest.exists() or dest.stat().st_size == 0:
            raise FFmpegProcessingError("FFmpeg produced no output file.")
        return dest

    def _audio_codec_args(self, source: Path, target: AudioTarget) -> list[str]:
        # Remux without re-encoding when the source already carries a native codec
        # for this container (cheap + lossless). We detect by source extension since
        # yt-dlp names the file after the chosen format's container.
        source_ext = source.suffix.lstrip(".").lower()
        if source_ext in target.native_acodecs or source_ext == target.container:
            return ["-c:a", "copy"]
        return ["-c:a", target.ffmpeg_codec]

    async def _run(self, args: list[str]) -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (OSError, ValueError) as exc:  # binary missing / bad args
            raise FFmpegProcessingError(f"ffmpeg could not be launched: {exc}") from exc

        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        except TimeoutError as exc:
            proc.kill()
            raise FFmpegProcessingError("ffmpeg timed out.") from exc

        if proc.returncode != 0:
            tail = stderr.decode(errors="replace").strip().splitlines()[-1:] or [""]
            _log.warning("ffmpeg_failed", returncode=proc.returncode, error=tail[0])
            raise FFmpegProcessingError("Audio conversion failed.")
