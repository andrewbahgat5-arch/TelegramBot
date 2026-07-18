"""YtdlpProvider — the sole V1 download provider (MASTER_PLAN 12.6.5, Task 5.3).

Wraps the ``yt-dlp`` binary as an async subprocess (no Python import of ``yt_dlp``;
this is the only module permitted to touch it — Section 12.6.9). Parses ``-J`` JSON
into a provider-agnostic :class:`MediaInfo`, maps vendor errors onto the domain
exceptions the registry interprets (Section 12.6.8), and implements ``health_check``.

Format extraction here is intentionally raw: it emits one option per usable yt-dlp
format. The provider-agnostic dedup/sort lives in ``services/format_extraction.py``
(Task 5.6) so it stays provider-independent.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import orjson

from core.logging import get_logger
from core.urls import detect_platform
from domain.entities.media import DownloadedFile, MediaFormatOption, MediaInfo
from domain.enums import MediaFormat, Quality
from domain.exceptions import (
    ExtractionFailedError,
    InfrastructureError,
    NoDownloadableMediaError,
    URLNotSupportedError,
    VideoUnavailableError,
)
from domain.protocols.downloader import (
    Capability,
    DownloadProgress,
    ProviderHealth,
    ProviderRetryElsewhere,
)
from infrastructure.downloader.routing import (
    DIRECT_ID,
    WARP_MAX_DOWNLOAD_BYTES,
    Egress,
    EgressEndpoint,
    EgressRegistry,
)

_T = TypeVar("_T")

_log = get_logger("infrastructure.downloader.providers.ytdlp")

_DEFAULT_EXTRACT_TIMEOUT = 30.0
_DEFAULT_DOWNLOAD_TIMEOUT = 600.0  # room for the slow WARP fallback on large 4K files
_DEFAULT_HEALTH_TIMEOUT = 10.0

# In-provider retry for metadata extraction (UX sprint #12). V1 runs a single provider, so
# registry failover is a no-op — a transient blip (rate-limit, bot-check, a flaky player-JS
# fetch) would otherwise surface as a hard "couldn't read that link" even though the very
# next attempt usually succeeds. Extraction is cheap and idempotent, so retry it a couple of
# times with a short backoff before giving up. Downloads are NOT retried here (expensive, and
# the job layer already re-queues).
_EXTRACT_RETRIES = 2
_RETRY_BACKOFF_SECONDS = 0.5

# YouTube's interactive verification wall ("Sign in to confirm you're not a bot" — the
# apostrophe varies between ASCII and U+2019 across builds, hence the wildcard). Served
# per-video to flagged egress IPs; with --ignore-no-formats-error it yields rc=0 +
# metadata-only, so the stderr text is the ONLY place the real reason appears. Retrying
# does not help → VideoUnavailableError.
_BOT_CHECK_RE = re.compile(r"confirm you.{0,3}re not a bot", re.IGNORECASE)

# Platforms where a post legitimately carries images instead of video, so a
# no-formats result may still be deliverable as a photo. YouTube is absent by design:
# there are no image posts there, and a blocked extraction emits a storyboard that must
# never be delivered as a photo (see _to_media_info).
_IMAGE_CAPABLE_PLATFORMS = frozenset(
    {"generic", "twitter", "tiktok", "instagram", "facebook"}
)

# Machine-readable per-chunk progress on stdout (parsed in _run_with_progress). Prefix
# "DLP" disambiguates it from any other output; fields are downloaded/total/estimate.
_PROGRESS_TEMPLATE = (
    "download:DLP %(progress.downloaded_bytes)s "
    "%(progress.total_bytes)s %(progress.total_bytes_estimate)s"
)

# Fast download: aria2c with 16 parallel range connections. Requires an HTTP proxy (the
# residential proxy) — aria2c has no SOCKS support, so this never runs on the WARP path.
# aria2c reports progress only per completed stream, so the live bar is coarser here — an
# easy trade for a ~8x faster transfer (large 4K files finish in tens of seconds).
_ARIA2C_DOWNLOAD_ARGS = [
    "--downloader",
    "aria2c",
    "--downloader-args",
    "aria2c:-x16 -s16 -k1M --file-allocation=none --console-log-level=warn "
    "--max-tries=5 --retry-wait=2",
]

# Quality tiers keyed by their standard *short* side (the "Np" label) and by their
# standard *long* side. Real pixel dimensions are matched to the nearest tier rather
# than floored: wide/portrait videos have non-16:9 dimensions (e.g. 4K = 3840x2026),
# so a floor on raw height mislabels every tier one step down.
_TIER_BY_SHORT_EDGE: tuple[tuple[int, Quality], ...] = (
    (2160, Quality.P2160),
    (1440, Quality.P1440),
    (1080, Quality.P1080),
    (720, Quality.P720),
    (480, Quality.P480),
    (360, Quality.P360),
    (240, Quality.P240),
    (144, Quality.P144),
)
_TIER_BY_LONG_EDGE: tuple[tuple[int, Quality], ...] = (
    (3840, Quality.P2160),
    (2560, Quality.P1440),
    (1920, Quality.P1080),
    (1280, Quality.P720),
    (854, Quality.P480),
    (640, Quality.P360),
    (426, Quality.P240),
    (256, Quality.P144),
)
# yt-dlp's own resolution label, e.g. "1080p", "2160p60", "1440p Premium".
_NOTE_TIER_RE = re.compile(r"(\d{3,4})\s*p")

# yt-dlp stderr fragments → how the registry should react. Order matters: unsupported and
# genuine-content failures are permanent (do not retry); everything transient is retried /
# failed over. (UX sprint #12 reclassification.)
_UNSUPPORTED_MARKERS = ("unsupported url", "is not a valid url")
# Permanent: the content itself is gone/blocked — retrying cannot help.
_CONTENT_MARKERS = (
    "video unavailable",
    "private video",
    "this video is not available",
    "has been removed",
    "account has been terminated",
    "geo restricted",
    "geo-restricted",
    "members-only",
    "premieres in",
    "requested format is not available",
)
# Transient: rate-limits, anti-bot interstitials, and flaky player-JS / signature fetches
# that typically succeed on a retry. These previously fell through to a permanent
# ExtractionFailedError (or, for the bot-check, were miscategorised as "content"), which is
# exactly why a link that worked earlier could suddenly read as "private or removed" (#12).
_TRANSIENT_MARKERS = (
    "timed out",
    "temporary failure",
    "temporarily unavailable",
    "connection reset",
    "connection refused",
    "http error 5",
    "http error 429",
    "http error 403",  # GVS media URL / PO token expired mid-download — a retry re-mints it
    "too many requests",
    "rate-limit",
    "rate limit",
    "sign in to confirm",  # YouTube anti-bot interstitial — throttle-based, not permanent
    "confirm you're not a bot",
    "unable to extract",  # usually a stale player-JS / nsig fetch; a retry re-fetches it
    "failed to extract",
    "nsig",
    "unable to download webpage",
    # Interrupted media transfer (common on large 1080p+ streams through the WARP proxy):
    # a fragment 403s/resets, so the .part is gone when yt-dlp tries to finalise it. A
    # retry re-downloads from a fresh URL — empirically it then succeeds.
    "unable to download video data",
    "unable to rename",
    "content too short",
    "the read operation timed out",
    # Egress/proxy failures — an egress hiccup must fail over to the next in the plan,
    # not permanently fail the job (routing.plan_egress).
    "aria2c exited",
    "unable to connect to proxy",
    "connection to proxy",
    "proxy server",
)


class YtdlpProvider:
    def __init__(
        self,
        ytdlp_path: str = "yt-dlp",
        *,
        extract_timeout: float = _DEFAULT_EXTRACT_TIMEOUT,
        download_timeout: float = _DEFAULT_DOWNLOAD_TIMEOUT,
        proxy: str = "",
        warp_proxy: str = "",
        warp_max_download_bytes: int = WARP_MAX_DOWNLOAD_BYTES,
        egress_registry: EgressRegistry | None = None,
    ) -> None:
        self.name = "ytdlp"
        self.supported_platforms = {"*"}
        self.capabilities = {Capability.VIDEO, Capability.AUDIO}
        self.priority = 100
        self._bin = ytdlp_path
        self._extract_timeout = extract_timeout
        self._download_timeout = download_timeout
        # Per-egress proxies (see infrastructure.downloader.routing). WARP SOCKS carries
        # metadata + downloads up to the size split; the residential HTTP proxy carries
        # the large ones (WARP is bandwidth-capped and cannot use aria2c).
        self._warp_max_download_bytes = warp_max_download_bytes
        # Concrete endpoints (ids + addresses). A caller may inject a registry with extra
        # instances (warp-2, proxy-res-2); by default one endpoint per kind is built from
        # the configured addresses, which is behaviour-identical to before.
        self._egress = egress_registry or EgressRegistry.from_addresses(
            proxy=proxy, warp_proxy=warp_proxy
        )

    async def _run_egress_plan(
        self,
        platform: str,
        size_bytes: int | None,
        run: Callable[[EgressEndpoint], Awaitable[_T]],
        *,
        metadata_only: bool = False,
    ) -> _T:
        """Try each endpoint in the platform's policy order until one succeeds.

        A configured-but-transiently-failing endpoint falls over to the next; kinds with
        no configured endpoint are never planned. The last transient error is surfaced if
        every endpoint fails.

        ``run`` receives the whole :class:`EgressEndpoint` rather than a bare address, so
        callers can branch on its ``kind`` (aria2c cannot use SOCKS) and record its ``id``
        (cookie affinity is pinned per endpoint).
        """
        last_exc: Exception | None = None
        attempted = False
        for endpoint in self._egress.plan(
            platform,
            size_bytes=size_bytes,
            metadata_only=metadata_only,
            warp_max_bytes=self._warp_max_download_bytes,
        ):
            attempted = True
            try:
                return await run(endpoint)
            except (ProviderRetryElsewhere, InfrastructureError) as exc:
                last_exc = exc
                _log.warning(
                    "egress_attempt_failed",
                    platform=platform,
                    egress_id=endpoint.id,
                    egress_kind=str(endpoint.kind),
                    error=str(exc),
                )
        if not attempted:
            # Nothing configured for this platform's kinds — attempt DIRECT rather than
            # failing outright (the dev/test path, never production).
            return await run(EgressEndpoint(DIRECT_ID, Egress.DIRECT, ""))
        if last_exc is not None:
            raise last_exc
        raise ExtractionFailedError("No usable egress for this request.")

    async def extract_info(self, url: str) -> MediaInfo:
        # --ignore-no-formats-error: image-only sources (e.g. a Pinterest image pin) have no
        # *video* formats; without this yt-dlp exits non-zero ("No video formats found") and
        # we lose the metadata + image. With it, the info dict (incl. thumbnails) is returned
        # and we emit an IMAGE option below (guarded by platform in _to_media_info).
        # NO --no-warnings here: with --ignore-no-formats-error a blocked extraction still
        # exits 0, and the suppressed warning text is the only record of WHY there are no
        # formats (e.g. YouTube's bot-check wall) — we need it to classify the failure.
        base = [self._bin, "-J", "--no-playlist", "--ignore-no-formats-error"]
        platform = detect_platform(url)

        async def run(endpoint: EgressEndpoint) -> tuple[bytes, bytes]:
            # ``--proxy ""`` forces DIRECT (overrides any ambient config); a value routes it.
            return await self._run_with_retries(
                [*base, "--proxy", endpoint.address, url], timeout_s=self._extract_timeout
            )

        stdout, stderr = await self._run_egress_plan(platform, None, run, metadata_only=True)
        try:
            info: dict[str, Any] = orjson.loads(stdout)
        except orjson.JSONDecodeError as exc:
            raise ExtractionFailedError("Could not parse media metadata.") from exc
        try:
            return self._to_media_info(url, info)
        except ProviderRetryElsewhere:
            # No playable formats on a named platform — the stderr warnings say why.
            stderr_text = stderr.decode(errors="replace").strip()
            if _BOT_CHECK_RE.search(stderr_text):
                _log.warning(
                    "ytdlp_bot_check_wall", platform=platform, stderr=stderr_text[:300]
                )
                raise VideoUnavailableError(
                    "The site is demanding interactive verification for this video."
                ) from None
            if stderr_text:
                _log.warning(
                    "ytdlp_no_formats_stderr", platform=platform, stderr=stderr_text[:300]
                )
            raise

    async def _run_with_retries(self, args: list[str], *, timeout_s: float) -> tuple[bytes, bytes]:
        """Run yt-dlp, retrying only *transient* failures a few times (#12)."""
        attempt = 0
        while True:
            try:
                return await self._run(args, timeout_s=timeout_s)
            except ProviderRetryElsewhere as exc:
                attempt += 1
                if attempt > _EXTRACT_RETRIES:
                    _log.warning("ytdlp_extract_gave_up", attempts=attempt, error=str(exc))
                    raise
                _log.info("ytdlp_extract_retry", attempt=attempt, error=str(exc))
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS * attempt)

    async def download(
        self,
        media: MediaInfo,
        format_: MediaFormat,
        quality: Quality,
        dest: Path,
        *,
        progress_cb: DownloadProgress | None = None,
    ) -> DownloadedFile:
        dest.mkdir(parents=True, exist_ok=True)
        out_template = str(dest / f"{media.video_id}.%(ext)s")
        if format_ is MediaFormat.IMAGE:
            # Fetch the image URL directly (no format selector / no merge). The URL was
            # stashed on the IMAGE option at extraction time. Images are tiny — no bar.
            image_url = _selected_image_url(media)
            if not image_url:
                raise ExtractionFailedError("No image URL to download.")
            args = [self._bin, "--no-playlist", "--no-warnings", "-o", out_template, image_url]
            await self._run(args, timeout_s=self._download_timeout)
        else:
            selector = _format_selector(media, format_, quality)
            base = [self._bin, "-f", selector, "--no-playlist", "--no-warnings"]
            if format_ is MediaFormat.VIDEO:
                # Merge into an mp4 container so Telegram plays it inline (sendVideo). The
                # selector already prefers H.264/AAC; VP9/AV1-only tiers stay in their
                # native container and Telegram falls back to a document.
                base += ["--merge-output-format", "mp4"]
            if progress_cb is not None:
                # Emit machine-parseable per-chunk progress on stdout so the caller can
                # render a live bar (merged video reports one 0→100 pass per stream).
                base += ["--newline", "--progress-template", _PROGRESS_TEMPLATE]
            tail = ["-o", out_template, media.source_url]
            size = _selected_size_bytes(media, format_, quality)
            await self._download_via_egress(
                base, tail, dest, media.video_id, media.platform, size, progress_cb
            )
        produced = sorted(dest.glob(f"{media.video_id}.*"), key=lambda p: p.stat().st_size)
        if not produced:
            raise ExtractionFailedError("Download produced no file.")
        path = produced[-1]
        return DownloadedFile(
            path=path, size_bytes=path.stat().st_size, format=format_, quality=quality
        )

    async def _download_via_egress(
        self,
        base: list[str],
        tail: list[str],
        dest: Path,
        video_id: str,
        platform: str,
        size_bytes: int | None,
        progress_cb: DownloadProgress | None,
    ) -> None:
        """Download through the platform's egress plan (routing.plan_egress).

        Over an HTTP egress (DIRECT / residential PROXY) the fast aria2c path runs — 16
        parallel connections, ~50 MB/s vs. ~6 MB/s single-stream. WARP is SOCKS, which
        aria2c can't use, so that egress downloads natively. A failed egress wipes its
        partial output and falls over to the next in the plan.
        """

        first = True

        async def run(endpoint: EgressEndpoint) -> None:
            nonlocal first
            if not first:  # wipe the previous egress's partial before re-downloading
                for leftover in dest.glob(f"{video_id}.*"):
                    leftover.unlink(missing_ok=True)
            first = False
            args = [*base, "--proxy", endpoint.address]
            if endpoint.kind is not Egress.WARP:  # aria2c speaks HTTP, not SOCKS (WARP)
                args += _ARIA2C_DOWNLOAD_ARGS
            await self._invoke_download([*args, *tail], progress_cb)

        await self._run_egress_plan(platform, size_bytes, run)

    async def _invoke_download(
        self, args: list[str], progress_cb: DownloadProgress | None
    ) -> None:
        if progress_cb is not None:
            await self._run_with_progress(
                args, timeout_s=self._download_timeout, progress_cb=progress_cb
            )
        else:
            await self._run(args, timeout_s=self._download_timeout)

    async def health_check(self) -> ProviderHealth:
        try:
            await self._run([self._bin, "--version"], timeout_s=_DEFAULT_HEALTH_TIMEOUT)
        except Exception:
            return ProviderHealth.UNAVAILABLE
        return ProviderHealth.OK

    # --- subprocess + error mapping ---------------------------------------
    async def _run(self, args: list[str], *, timeout_s: float) -> tuple[bytes, bytes]:
        """Run yt-dlp to completion → ``(stdout, stderr)``; maps non-zero exits to
        domain errors. stderr is returned even on success — with
        ``--ignore-no-formats-error`` the reason an extraction produced no formats
        exists only there."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (OSError, ValueError) as exc:  # binary missing / bad args
            raise InfrastructureError(f"yt-dlp could not be launched: {exc}") from exc

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except TimeoutError as exc:
            proc.kill()
            raise ProviderRetryElsewhere("yt-dlp timed out.") from exc

        if proc.returncode != 0:
            decoded = stderr.decode(errors="replace")
            error = _map_error(decoded)
            # Always log *why* an extraction/download failed — previously the yt-dlp stderr
            # was discarded, so intermittent failures (#12) were undiagnosable. Truncated to
            # keep logs readable; the mapped class says whether we retry or surface it.
            _log.warning(
                "ytdlp_nonzero_exit",
                returncode=proc.returncode,
                mapped=type(error).__name__,
                stderr=decoded.strip()[:500],
            )
            raise error
        return stdout, stderr

    async def _run_with_progress(
        self, args: list[str], *, timeout_s: float, progress_cb: DownloadProgress
    ) -> None:
        """Run a download, streaming stdout to feed ``progress_cb`` live byte counts.

        stderr is buffered for error mapping (same as :meth:`_run`); progress callback
        errors are swallowed so a flaky Telegram edit never fails the download.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (OSError, ValueError) as exc:
            raise InfrastructureError(f"yt-dlp could not be launched: {exc}") from exc

        stderr_chunks: list[bytes] = []

        async def _drain_stderr() -> None:
            assert proc.stderr is not None
            async for line in proc.stderr:
                stderr_chunks.append(line)

        async def _read_stdout() -> None:
            assert proc.stdout is not None
            async for raw in proc.stdout:
                parsed = _parse_progress(raw.decode(errors="replace"))
                if parsed is not None:
                    try:
                        await progress_cb(parsed[0], parsed[1])
                    except Exception:  # noqa: S110 - progress is best-effort
                        pass

        try:
            await asyncio.wait_for(
                asyncio.gather(_read_stdout(), _drain_stderr()), timeout=timeout_s
            )
            await proc.wait()
        except TimeoutError as exc:
            proc.kill()
            raise ProviderRetryElsewhere("yt-dlp timed out.") from exc

        if proc.returncode != 0:
            decoded = b"".join(stderr_chunks).decode(errors="replace")
            error = _map_error(decoded)
            _log.warning(
                "ytdlp_nonzero_exit",
                returncode=proc.returncode,
                mapped=type(error).__name__,
                stderr=decoded.strip()[:500],
            )
            raise error

    def _to_media_info(self, url: str, info: dict[str, Any]) -> MediaInfo:
        platform = detect_platform(url)
        duration = _opt_int(info.get("duration"))
        formats = tuple(_parse_formats(info.get("formats") or [], duration))
        title = str(info.get("title") or "Untitled")
        if not formats:
            # Image posts are a real content type on the social platforms (a photo tweet,
            # a TikTok photo carousel, an Instagram photo, a Pinterest pin), so those get
            # the image fallback and are delivered as a photo.
            #
            # YouTube is deliberately excluded: it has no image posts, and an extraction
            # blocked by the bot-check wall still emits metadata + a storyboard under
            # ``--ignore-no-formats-error``. Delivering that would hand the user a
            # storyboard grid instead of their video (the original bug). YouTube walls are
            # classified upstream in :meth:`extract_info`; anything reaching here with no
            # formats genuinely has no downloadable media.
            image_url = _best_image_url(info) if platform in _IMAGE_CAPABLE_PLATFORMS else None
            if image_url:
                # yt-dlp labels image pins "Pinterest video #<id>"; the human text lives
                # in description — prefer it for a clean caption.
                desc = info.get("description")
                if isinstance(desc, str) and desc.strip():
                    title = desc.strip()[:200]
                formats = (
                    MediaFormatOption(
                        format=MediaFormat.IMAGE,
                        quality=Quality.IMAGE,
                        approx_size_bytes=_opt_int(
                            info.get("filesize") or info.get("filesize_approx")
                        ),
                        provider_format_id=image_url,
                        codec="image",
                    ),
                )
            elif platform in _IMAGE_CAPABLE_PLATFORMS:
                # Read the post fine; it simply carries nothing downloadable (a text-only
                # tweet, a poll, a link preview). Permanent — telling the user to "try
                # again" sent people into retry loops on posts that can never work.
                raise NoDownloadableMediaError(
                    "The post contains no downloadable video, audio or image."
                )
            else:
                # YouTube with no formats and no wall signature: extraction really did
                # fail. Keep this transient so the retry/failover path still applies.
                raise ProviderRetryElsewhere(
                    "No playable formats were found — the site returned only metadata "
                    "(often a temporary block). Please try again."
                )
        return MediaInfo(
            platform=platform,
            video_id=str(info.get("id") or ""),
            title=title,
            source_url=str(info.get("webpage_url") or url),
            duration=duration,
            thumbnail_url=info.get("thumbnail"),
            formats=formats,
            raw=_curated_metadata(info),
        )


_IMAGE_EXTS = frozenset(
    {"jpg", "jpeg", "png", "webp", "gif", "bmp", "tiff", "tif", "avif", "heic", "jfif"}
)


def _looks_like_image(url: str) -> bool:
    tail = url.split("?", 1)[0].rsplit("/", 1)[-1].lower()
    return "." in tail and tail.rsplit(".", 1)[-1] in _IMAGE_EXTS


def _parse_progress(line: str) -> tuple[int, int | None] | None:
    """Parse a ``DLP <downloaded> <total> <estimate>`` progress line → (downloaded, total).

    ``total`` falls back to the estimate, then None (unknown size). Non-progress lines
    and unparseable counts return None.
    """
    parts = line.split()
    if len(parts) < 3 or parts[0] != "DLP":
        return None
    downloaded = _opt_int(parts[1])
    if downloaded is None:
        return None
    total = _opt_int(parts[2])
    if total is None and len(parts) >= 4:
        total = _opt_int(parts[3])  # total_bytes_estimate
    return downloaded, total


def _is_storyboard(fmt: dict[str, Any]) -> bool:
    """A YouTube storyboard (``sb0``/``sb1``/… — a grid of frame thumbnails, ext mhtml).

    These are never real content; treating one as an image is exactly the bug that
    delivered a storyboard grid instead of the video.
    """
    return (
        str(fmt.get("format_id") or "").startswith("sb")
        or str(fmt.get("ext") or "").lower() == "mhtml"
        or "storyboard" in str(fmt.get("format_note") or "").lower()
    )


def _best_image_url(info: dict[str, Any]) -> str | None:
    """The highest-resolution still image for an image-only source (any site), or None.

    Works generically, not just for Pinterest:
      1. a concrete image *format* (direct image links / extractors that expose the
         picture as a format),
      2. a full-resolution ``/originals/`` thumbnail (Pinterest), else the largest
         thumbnail by pixel area,
      3. a top-level image ``url``, else the ``thumbnail`` preview.
    """
    for fmt in info.get("formats") or []:
        if _is_storyboard(fmt):
            continue  # a storyboard contact-sheet is never deliverable content
        url = fmt.get("url")
        if isinstance(url, str) and (
            str(fmt.get("ext") or "").lower() in _IMAGE_EXTS or _looks_like_image(url)
        ):
            return url
    thumbs = [t for t in (info.get("thumbnails") or []) if isinstance(t.get("url"), str)]
    originals = [t["url"] for t in thumbs if "/originals/" in t["url"]]
    if originals:
        return originals[-1]
    if thumbs:
        return max(
            thumbs,
            key=lambda t: (_opt_int(t.get("width")) or 0) * (_opt_int(t.get("height")) or 0),
        )["url"]
    top = info.get("url")
    if isinstance(top, str) and _looks_like_image(top):
        return top
    thumb = info.get("thumbnail")
    return thumb if isinstance(thumb, str) else None


def _selected_image_url(media: MediaInfo) -> str | None:
    for option in media.formats:
        if option.format is MediaFormat.IMAGE and option.provider_format_id:
            return option.provider_format_id
    return None


def _reason(stderr: str) -> str:
    """The first ERROR/WARNING line of yt-dlp's stderr, condensed for diagnostics.

    Exception messages are internal only (user-facing text comes from the catalog via
    ``translation_key``), and they are what ``error_logs.message`` records — so the
    real provider reason is carried here. Without it every row read "Extraction
    failed." and the cause was unrecoverable once container logs rotated.
    """
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    # An ERROR line states the actual failure; warnings are usually incidental noise
    # ("No title found in player responses…") that precedes it.
    for prefix in ("ERROR:", "WARNING:"):
        for line in lines:
            if line.upper().startswith(prefix):
                return line[:200]
    return lines[0][:200] if lines else ""


def _map_error(stderr: str) -> Exception:
    lowered = stderr.lower()
    reason = _reason(stderr)
    suffix = f" [{reason}]" if reason else ""
    if any(m in lowered for m in _UNSUPPORTED_MARKERS):
        return URLNotSupportedError(f"This URL is not supported.{suffix}")
    if any(m in lowered for m in _CONTENT_MARKERS):
        return ExtractionFailedError(f"This content is unavailable.{suffix}")
    if any(m in lowered for m in _TRANSIENT_MARKERS):
        return ProviderRetryElsewhere(f"Transient extractor error.{suffix}")
    # Unknown non-zero exit: treat as a content/extraction failure (do not fail over
    # blindly — the registry stops on ExtractionFailedError, Section 12.6.8).
    return ExtractionFailedError(f"Extraction failed.{suffix}")


def _is_hls(fmt: dict[str, Any]) -> bool:
    """A YouTube HLS/manifest format (``protocol`` m3u8). These mirror the DASH streams
    but carry no reliable ``filesize`` and an inflated ``tbr``, so their size can only be
    (mis)estimated — the source of the displayed-vs-actual size mismatch."""
    return "m3u8" in str(fmt.get("protocol") or "").lower()


def _parse_formats(
    raw_formats: list[dict[str, Any]], duration: int | None
) -> list[MediaFormatOption]:
    """Build provider-agnostic options with already-accurate, audio-inclusive sizes.

    Sizing rules (fixes the non-monotonic display, Sprint 6 follow-up):
    * Size = ``filesize`` / ``filesize_approx`` when present, else estimated from the
      stream's bitrate times duration (``tbr``/``abr``) — so tiers without a reported
      size still order correctly.
    * A **video-only** stream's size has the best audio stream's size added (it will be
      muxed with audio at download time). A **muxed** stream already includes audio, so
      nothing is added — this is what previously double-counted (e.g. 360p > 1080p).
    * Audio is offered whenever the media has *any* audio, including muxed-only sources
      like TikTok (a generic audio option is emitted so the per-codec catalog expands).
    """
    video_rows: list[_VideoRow] = []
    audio_options: list[MediaFormatOption] = []
    best_audio_size = 0
    mp4a_audio_size = 0  # best m4a audio — what a VIDEO download actually merges
    has_audio = False

    for fmt in raw_formats:
        format_id = fmt.get("format_id")
        if not format_id:
            continue
        if _is_hls(fmt):
            # HLS/manifest duplicates of the DASH streams (e.g. YouTube format 96): no real
            # filesize and an inflated peak ``tbr`` that estimated a wildly wrong size (475
            # vs. the real 198 MB) — and, being "larger", it won the per-tier tie-break and
            # was both displayed and selected. Skip them; the DASH formats carry real sizes.
            continue
        size = _opt_int(fmt.get("filesize") or fmt.get("filesize_approx"))
        height, width = _opt_int(fmt.get("height")), _opt_int(fmt.get("width"))
        tbr, abr = _opt_float(fmt.get("tbr")), _opt_float(fmt.get("abr"))

        # Codec fields are advisory: some extractors (X/Twitter) report none at all.
        # An explicit "none" is authoritative and still excludes the stream — that is
        # what keeps YouTube storyboards (vcodec=acodec="none") out.
        v_state, a_state = _codec_state(fmt.get("vcodec")), _codec_state(fmt.get("acodec"))
        # A frame size means it carries video, whatever the codec field says.
        has_v = v_state == "present" or (v_state == "unknown" and bool(height))
        # Unreported audio: a progressive stream is muxed (X's http-* formats are), and
        # a stream with a bitrate but no frame size is audio-only.
        has_a = a_state == "present" or (
            a_state == "unknown" and (has_v or bool(abr and not height))
        )
        has_audio = has_audio or has_a

        if has_v and height:
            est = size or _bitrate_size(tbr, duration)
            video_rows.append(
                _VideoRow(
                    quality=_quality_for_format(width, height, fmt.get("format_note")),
                    size=est,
                    format_id=str(format_id),
                    codec=_codec_family(fmt.get("vcodec")),
                    is_muxed=has_a,
                )
            )
        elif not has_v and has_a:
            acodec = _codec_family(fmt.get("acodec"))
            est = size or _bitrate_size(abr or tbr, duration)
            if est:
                best_audio_size = max(best_audio_size, est)
                if acodec == "mp4a":  # the codec the video selector merges (bestaudio[mp4a])
                    mp4a_audio_size = max(mp4a_audio_size, est)
            audio_options.append(
                MediaFormatOption(
                    format=MediaFormat.AUDIO,
                    quality=Quality.AUDIO,
                    approx_size_bytes=est,
                    provider_format_id=str(format_id),
                    codec=acodec,
                    asr=_opt_int(fmt.get("asr")),
                    channels=_opt_int(fmt.get("audio_channels")),
                )
            )

    # A video is merged with the best *m4a* audio (see _format_selector), so size the merged
    # file with that exact stream — keeping the displayed size in step with the real file —
    # falling back to the best audio overall when a source has no m4a.
    merge_audio_size = mp4a_audio_size or best_audio_size
    options: list[MediaFormatOption] = [
        MediaFormatOption(
            format=MediaFormat.VIDEO,
            quality=row.quality,
            approx_size_bytes=_video_size(row, merge_audio_size),
            provider_format_id=row.format_id,
            codec=row.codec,
        )
        for row in video_rows
    ]
    options.extend(audio_options)

    # Muxed-only sources (e.g. TikTok) expose no audio-only stream — still offer audio,
    # extracted from the best stream at download time (selector ``bestaudio/best``).
    if has_audio and not audio_options:
        options.append(
            MediaFormatOption(
                format=MediaFormat.AUDIO,
                quality=Quality.AUDIO,
                approx_size_bytes=_best_muxed_audio_size(raw_formats, duration),
                provider_format_id=None,
                codec="audio",
            )
        )
    return options


@dataclass(frozen=True, slots=True)
class _VideoRow:
    quality: Quality
    size: int | None
    format_id: str
    codec: str | None
    is_muxed: bool


def _video_size(row: _VideoRow, best_audio_size: int) -> int | None:
    if row.size is None:
        return None
    # Video-only streams gain the audio that will be muxed in; muxed streams already
    # contain it, so adding again would double-count.
    return row.size if row.is_muxed or not best_audio_size else row.size + best_audio_size


def _best_muxed_audio_size(raw_formats: list[dict[str, Any]], duration: int | None) -> int | None:
    abrs = [_opt_float(f.get("abr")) for f in raw_formats]
    best = max((a for a in abrs if a), default=None)
    return _bitrate_size(best, duration)


def _present(codec: object) -> bool:
    return bool(codec) and codec != "none"


def _codec_state(value: object) -> str:
    """Tri-state reading of a yt-dlp ``vcodec``/``acodec`` field.

    yt-dlp distinguishes two things that :func:`_present` used to collapse into one:

    * the literal string ``"none"`` — the extractor is telling us this stream
      definitely has no such track (a YouTube storyboard is ``vcodec="none"``);
    * a missing / ``None`` value — the extractor simply did not report a codec.

    Treating "unreported" as "absent" silently discarded every X/Twitter progressive
    format (``http-256``/``http-832``/``http-2176`` carry a real height and filesize
    but no codec strings), so X links produced zero options and surfaced to users as
    "no playable formats". Returns ``"present" | "absent" | "unknown"``.
    """
    if value is None or value == "":
        return "unknown"
    return "absent" if value == "none" else "present"


def _bitrate_size(kbps: float | None, duration: int | None) -> int | None:
    """Estimate bytes from a bitrate (kbps) over a duration (s): kbps*1000/8*seconds."""
    if not kbps or not duration:
        return None
    return int(kbps * 1000 / 8 * duration)


def _codec_family(codec: object) -> str | None:
    """Reduce a vendor codec string (``avc1.640028``, ``mp4a.40.2``) to its family."""
    if not isinstance(codec, str) or not codec:
        return None
    return codec.split(".", 1)[0].strip().lower()


def _quality_for_format(width: int | None, height: int | None, format_note: str | None) -> Quality:
    """Resolve a display quality tier robustly across aspect ratios.

    Prefers yt-dlp's own ``format_note`` label (e.g. "2160p60"); otherwise snaps the
    format's longer edge to the nearest standard tier. Snapping to *nearest* (not a
    floor) is what fixes 4K on wide videos (3840x2026 → 2160p, not 1440p).
    """
    if format_note:
        match = _NOTE_TIER_RE.search(format_note)
        if match:
            return _nearest_tier(int(match.group(1)), _TIER_BY_SHORT_EDGE)
    if width and height:
        # Both edges known: the longer edge identifies the tier for any aspect ratio.
        return _nearest_tier(max(width, height), _TIER_BY_LONG_EDGE)
    if height:  # height-only: assume landscape, match the short-edge ladder
        return _nearest_tier(height, _TIER_BY_SHORT_EDGE)
    if width:
        return _nearest_tier(width, _TIER_BY_LONG_EDGE)
    return Quality.P144


def _nearest_tier(value: int, ladder: tuple[tuple[int, Quality], ...]) -> Quality:
    return min(ladder, key=lambda tier: abs(tier[0] - value))[1]


_QUALITY_HEIGHT: dict[Quality, int] = {
    Quality.P144: 144,
    Quality.P240: 240,
    Quality.P360: 360,
    Quality.P480: 480,
    Quality.P720: 720,
    Quality.P1080: 1080,
    Quality.P1440: 1440,
    Quality.P2160: 2160,
}


def _selected_video_format_id(media: MediaInfo, quality: Quality) -> str | None:
    """The exact yt-dlp ``format_id`` the user was shown for ``quality`` (D-046).

    The quality keyboard offered one option per tier, each carrying the ``format_id``
    whose size was displayed. Downloading *that* format guarantees the delivered
    resolution and size match what was selected (#28/#29) — instead of re-deriving via a
    height cap, which could resolve to a different (or higher) format.
    """
    for option in media.formats:
        if (
            option.format is MediaFormat.VIDEO
            and option.quality is quality
            and option.provider_format_id
        ):
            return option.provider_format_id
    return None


def _selected_size_bytes(
    media: MediaInfo, format_: MediaFormat, quality: Quality
) -> int | None:
    """Expected size of the chosen (format, quality), for the egress policy — best-effort.

    Feeds ``routing.plan_egress(size_bytes=...)`` so a future size-based rule (WARP under
    500 MB, proxy at/over) needs no change here. ``None`` when the size is unknown.
    """
    for option in media.formats:
        if option.format is format_ and option.quality is quality:
            return option.approx_size_bytes
    return None


def _format_selector(media: MediaInfo, format_: MediaFormat, quality: Quality) -> str:
    """yt-dlp ``-f`` selector. Video always merges audio so downloads are never silent.

    Primary path (D-046): download the **exact** ``format_id`` that was offered for the
    chosen tier, so the delivered quality and size match the displayed option (#28/#29).
    A video-only format is merged with the best audio; an already-muxed format falls back
    to itself. If the id is unavailable (stale/odd source) we fall back to a height-capped
    ``bestvideo+bestaudio`` — **never** an uncapped ``best``, so the delivered video can
    never exceed the selected tier. Audio uses ``bestaudio/best`` (then transcoded).
    """
    if format_ is MediaFormat.AUDIO:
        return "bestaudio/best"

    fid = _selected_video_format_id(media, quality)
    if fid:
        return f"{fid}+bestaudio[acodec^=mp4a]/{fid}+bestaudio/{fid}"

    height = _QUALITY_HEIGHT.get(quality)
    if height is None:  # no tier height (e.g. BEST) — best available, still no over-cap
        return "bestvideo+bestaudio/best"
    cap = f"[height<={height}]"
    # Prefer H.264 video + AAC audio in an mp4 (Telegram plays mp4 inline); then any
    # codec at the tier; then any progressive format. Every branch caps the height.
    return (
        f"bestvideo{cap}[vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
        f"bestvideo{cap}[ext=mp4]+bestaudio[ext=m4a]/"
        f"bestvideo{cap}+bestaudio/best{cap}"
    )


def _curated_metadata(info: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "extractor",
        "uploader",
        "uploader_id",
        "view_count",
        "like_count",
        "webpage_url",
        # Extra fields surfaced in the chooser caption (best-effort; providers vary).
        "upload_date",
        "comment_count",
        "channel",
        "channel_follower_count",
        # Canonical links for the chooser's inline hyperlinks (title → video, name → channel).
        "channel_url",
        "uploader_url",
    )
    return {k: info[k] for k in keys if info.get(k) is not None}


def _opt_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _opt_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
