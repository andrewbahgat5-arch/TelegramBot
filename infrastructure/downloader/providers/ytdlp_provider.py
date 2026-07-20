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
import contextlib
import dataclasses
import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import orjson

from core.logging import get_logger
from core.urls import detect_platform, extract_video_id
from domain.entities.media import (
    CarouselItem,
    DownloadedFile,
    MediaFormatOption,
    MediaInfo,
)
from domain.enums import MediaFormat, Quality
from domain.exceptions import (
    AuthRequiredError,
    ExtractionFailedError,
    InfrastructureError,
    NoDownloadableMediaError,
    URLNotSupportedError,
    VideoUnavailableError,
)
from domain.protocols.cookies import CookieProviderProtocol
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


@dataclass
class _CookieRun:
    """Mutable handle for one leased run: the env to pass, and the outcome to report."""

    lease: Any | None
    returncode: int = 0
    stderr: str = ""

    @property
    def env(self) -> dict[str, str] | None:
        """Subprocess environment, or None to inherit unchanged (no cookie leased).

        ``YTDLP_COOKIE_FILE`` is what ``deploy/ytdlp-wrapper.sh`` reads to pick the jar,
        so selection stays in Python while the wrapper keeps owning the safe file
        mechanics (private copy, flock, merge write-back).
        """
        if self.lease is None:
            return None
        return {**os.environ, "YTDLP_COOKIE_FILE": str(self.lease.path)}


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
# A playlist can hold thousands of videos. Listing every one costs time and cache
# space, and nobody pages through 5000 items in Telegram — so the gallery shows the
# first N and SAYS SO, rather than silently truncating.
MAX_PLAYLIST_ITEMS = 50

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
# The site will only serve this to a logged-in session. Permanent for us by design —
# we hold no session for these platforms, so retry/failover/cookie-swap cannot help,
# and the user needs to be told that plainly (AuthRequiredError) rather than getting a
# generic "extraction failed" they will keep retrying.
#
# Checked BEFORE _CONTENT_MARKERS and _TRANSIENT_MARKERS. Two deliberate calls:
#   * Instagram's "Requested content is not available, rate-limit reached or login
#     required" also contains the transient marker "rate-limit". Anonymous Instagram
#     extraction is login-gated in practice, so auth wins — "try again later" would be
#     a lie on a post that can never work anonymously.
#   * "sign in to confirm your age" is listed in full, NOT as a "sign in to confirm"
#     prefix, so it cannot swallow YouTube's "sign in to confirm you're not a bot" —
#     that is the anti-bot wall (a route problem, transient) and must stay transient.
_AUTH_REQUIRED_MARKERS = (
    "login required",
    "requires authentication",
    "for the authentication",  # "...use --cookies for the authentication"
    "--cookies-from-browser",
    "you must be logged in",
    "log in to",
    "logged-in",  # Instagram: "accessible in your browser without being logged-in"
    "empty media response",  # Instagram's anonymous-request answer
    "only available for registered users",
    "sign in to confirm your age",
    "age-restricted",
    "age restricted",
    "this post is private",
    "account is private",
    "friends-only",
    "followers only",
)
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
        cookies: CookieProviderProtocol | None = None,
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
        # The cookie pool. None ⇒ no pool wired (dev/tests, or a deployment that has not
        # imported any cookies): every run then goes out anonymously, which is exactly
        # the pre-pool behaviour.
        self._cookies = cookies

    @contextlib.asynccontextmanager
    async def _cookie_session(
        self, platform: str, endpoint: EgressEndpoint
    ) -> AsyncIterator[_CookieRun]:
        """Lease a cookie for this endpoint, then report how the run went.

        Yields a small handle carrying the subprocess ``env`` (with
        ``YTDLP_COOKIE_FILE`` pointing at the leased jar, which the wrapper picks up).
        The lease is always released, and a raised error is reported as a failed run so
        the pool sees the outcome even when the caller re-raises.
        """
        lease = None
        if self._cookies is not None:
            with contextlib.suppress(Exception):  # the pool must never block a download
                lease = await self._cookies.acquire(platform=platform, egress_id=endpoint.id)
        handle = _CookieRun(lease)
        try:
            yield handle
        except Exception as exc:
            handle.returncode = 1
            handle.stderr = str(getattr(exc, "provider_stderr", "") or str(exc))
            raise
        finally:
            if lease is not None and self._cookies is not None:
                with contextlib.suppress(Exception):
                    await self._cookies.report_run(
                        lease, returncode=handle.returncode, stderr=handle.stderr
                    )
                    await self._cookies.release(lease)

    async def canary_check(
        self, *, cookie_path: Path, egress_id: str | None = None, url: str = ""
    ) -> tuple[bool, str]:
        """Verify a cookie file with one real extraction (DESIGN_COOKIE_POOL.md §10).

        Used before an uploaded cookie is accepted, and by the "Test now" admin action.
        Runs outside the pool entirely — the cookie under test is passed explicitly, so
        a broken upload can never be leased to a real request just to find out.
        """
        target = url or "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        endpoint = (
            self._egress.get(egress_id)
            if egress_id
            else next(iter(self._egress.plan("youtube", metadata_only=True)), None)
        )
        args = [
            self._bin,
            "-J",
            "--no-playlist",
            "--ignore-no-formats-error",
            "--proxy",
            endpoint.address if endpoint else "",
            target,
        ]
        env = {**os.environ, "YTDLP_COOKIE_FILE": str(cookie_path)}
        try:
            stdout, stderr = await self._run(args, timeout_s=self._extract_timeout, env=env)
        except Exception as exc:
            return False, str(exc)[:200]
        try:
            info: dict[str, Any] = orjson.loads(stdout)
        except orjson.JSONDecodeError:
            return False, "yt-dlp returned no parseable metadata"
        formats = info.get("formats") or []
        if not formats:
            detail = _reason(stderr.decode(errors="replace")) or "no playable formats"
            return False, detail
        return True, f"{len(formats)} formats via {endpoint.id if endpoint else 'direct'}"

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

    async def extract_info(self, url: str, *, item_index: int | None = None) -> MediaInfo:
        # --ignore-no-formats-error: image-only sources (e.g. a Pinterest image pin) have no
        # *video* formats; without this yt-dlp exits non-zero ("No video formats found") and
        # we lose the metadata + image. With it, the info dict (incl. thumbnails) is returned
        # and we emit an IMAGE option below (guarded by platform in _to_media_info).
        # NO --no-warnings here: with --ignore-no-formats-error a blocked extraction still
        # exits 0, and the suppressed warning text is the only record of WHY there are no
        # formats (e.g. YouTube's bot-check wall) — we need it to classify the failure.
        # A PLAYLIST url (youtube.com/playlist?list=…, a channel, a mix) is listed
        # flat: its entries are stubs with no formats whatever we ask for, so paying for
        # full extraction buys nothing. Measured on a 13-video playlist: 17.3s / 816 KB
        # full vs 2.4s / 18 KB flat, for identical entries. The chosen video is then
        # extracted normally, by its own URL, when the user picks it.
        #
        # --no-playlist stays for everything else: it is what stops a `watch?v=…&list=…`
        # link from expanding into the whole playlist when the user asked for one video.
        listing = _is_playlist_url(url) and item_index is None
        base = [self._bin, "-J", "--ignore-no-formats-error"]
        base += ["--flat-playlist"] if listing else ["--no-playlist"]
        platform = detect_platform(url)

        async def run(endpoint: EgressEndpoint) -> tuple[bytes, bytes]:
            # ``--proxy ""`` forces DIRECT (overrides any ambient config); a value routes it.
            async with self._cookie_session(platform, endpoint) as session:
                out, err = await self._run_with_retries(
                    [*base, "--proxy", endpoint.address, url],
                    timeout_s=self._extract_timeout,
                    env=session.env,
                )
                # A clean exit can still carry the bot-check wall; the classifier reads
                # stderr to decide whether the cookie earned any credit.
                session.stderr = err.decode(errors="replace")
                return out, err

        stdout, stderr = await self._run_egress_plan(platform, None, run, metadata_only=True)
        try:
            parsed: Any = orjson.loads(stdout)
        except orjson.JSONDecodeError as exc:
            raise ExtractionFailedError("Could not parse media metadata.") from exc
        if not isinstance(parsed, dict):
            # An extractor that matched the URL but returned nothing prints a bare `null`
            # and exits 0 (yt-dlp: "Extractor telegram:embed returned nothing"). That is
            # valid JSON, so the decode above passes and the old code called
            # _to_media_info(url, None) → AttributeError on None.get, escaping the
            # provider as an untyped crash. The site is matched but unusable → permanent.
            reason = _reason(stderr.decode(errors="replace"))
            raise URLNotSupportedError(
                "This link is not supported." + (f" [{reason}]" if reason else "")
            )
        info: dict[str, Any] = parsed
        # A multi-item post (Instagram carousel) arrives as a playlist: the post itself
        # has NO formats and the real media lives in `entries`. Reading only the
        # top-level formats made every carousel look empty — a public 5x1440p post
        # surfaced to the user as "no downloadable media".
        entries = [e for e in (info.get("entries") or []) if isinstance(e, dict)]
        total_entries = len(entries)
        entries = entries[:MAX_PLAYLIST_ITEMS]
        if entries:
            try:
                return self._from_carousel(
                    url, info, entries, item_index, total=total_entries
                )
            except _NeedsOwnExtractionError as needs:
                # A playlist entry: extract it on its OWN url. That is an ordinary
                # single-video extraction, so it reuses this whole method — cookies,
                # egress plan, retries, classification — rather than duplicating any of
                # it. The index is kept so the item still has a distinct identity and
                # the gallery can send the user back to the right slot.
                item = await self.extract_info(needs.url)
                return dataclasses.replace(
                    item,
                    video_id=f"{item.video_id}#{needs.index}",
                    carousel_index=needs.index,
                )
        try:
            return self._to_media_info(url, info)
        except NoDownloadableMediaError:
            # "Nothing downloadable here" and "you are not allowed to see what is here"
            # are indistinguishable from the info dict alone — a login-walled Instagram
            # post returns the same empty-formats shape as a text-only tweet. Under
            # --ignore-no-formats-error the run exits 0, so _map_error never sees this
            # stderr; it is read here instead. Auth wins when the site said so.
            stderr_text = stderr.decode(errors="replace").strip()
            if any(m in stderr_text.lower() for m in _AUTH_REQUIRED_MARKERS):
                _log.info(
                    "ytdlp_auth_required", platform=platform, stderr=stderr_text[:300]
                )
                raise AuthRequiredError(
                    "This content requires a logged-in session."
                    + (f" [{_reason(stderr_text)}]" if stderr_text else "")
                ) from None
            raise
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

    def _from_carousel(
        self,
        url: str,
        post: dict[str, Any],
        entries: list[dict[str, Any]],
        item_index: int | None,
        total: int | None = None,
    ) -> MediaInfo:
        """Turn a multi-item post into either an item INDEX or one chosen ITEM.

        Two shapes come out of here:

        * ``item_index is None`` and there is more than one entry → an *index* result:
          no formats, but ``carousel_items`` listing what the user may pick. The caller
          shows an item picker, then calls back with the index.
        * an index (or a single-entry post) → the real :class:`MediaInfo` for that entry,
          tagged with ``carousel_index`` so ``download`` can re-address it.

        A single-entry post skips the picker entirely — asking someone to choose between
        one option is just an extra tap.
        """
        platform = detect_platform(url)
        if item_index is None and len(entries) > 1:
            post_artwork = _best_image_url(post)
            items = tuple(
                CarouselItem(
                    index=i,
                    title=str(entry.get("title") or f"Item {i}"),
                    kind=_entry_kind(entry),
                    height=_best_entry_height(entry),
                    duration=_opt_int(entry.get("duration")),
                    # Priority 4 (the post's own artwork) is the last resort, so an item
                    # whose entry carries no preview still renders inside the gallery.
                    thumbnail_url=_entry_thumbnail(entry) or post_artwork,
                    has_audio=_entry_has_audio(entry),
                )
                for i, entry in enumerate(entries, start=1)
            )
            return MediaInfo(
                platform=platform,
                video_id=str(post.get("id") or extract_video_id(url, platform) or ""),
                title=str(post.get("title") or "Untitled"),
                source_url=url,
                thumbnail_url=items[0].thumbnail_url if items else post_artwork,
                formats=(),
                raw={**post, "playlist_total": total or len(entries)},
                carousel_items=items,
            )

        index = 1 if item_index is None else item_index
        if not 1 <= index <= len(entries):
            raise URLNotSupportedError(
                f"That item does not exist in this post (1-{len(entries)})."
            )
        entry = entries[index - 1]
        # Two shapes of multi-item source, and they need opposite handling:
        #
        #   * A carousel entry (Instagram) carries its formats inline but NO url of its
        #     own — every slide shares the post's webpage_url — so it is flattened here
        #     and re-addressed at download time by --playlist-items.
        #   * A playlist entry (YouTube) is the reverse: no formats, but a real video
        #     url. Flattening it yields "no playable formats"; it has to be extracted
        #     on its own url, which is just an ordinary single-video extraction.
        own_url = _entry_own_url(entry)
        if own_url and not (entry.get("formats") or []):
            raise _NeedsOwnExtractionError(own_url, index)
        item = self._to_media_info(url, {**entry, "webpage_url": url})
        return dataclasses.replace(
            item,
            video_id=f"{item.video_id or post.get('id') or ''}#{index}",
            carousel_index=index,
        )

    async def _run_with_retries(
        self, args: list[str], *, timeout_s: float, env: dict[str, str] | None = None
    ) -> tuple[bytes, bytes]:
        """Run yt-dlp, retrying only *transient* failures a few times (#12)."""
        attempt = 0
        while True:
            try:
                return await self._run(args, timeout_s=timeout_s, env=env)
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
        # A carousel item's video_id carries a "#<n>" suffix to keep its cache/DB row
        # distinct from its siblings. That must not reach the filesystem, where "#" is
        # awkward in paths and output templates — the stem is sanitised for disk only.
        stem = _output_stem(media)
        out_template = str(dest / f"{stem}.%(ext)s")
        # Selecting one item of a multi-item post: entries share the post URL and some
        # format ids repeat across entries, so the 1-based playlist index is the only
        # unambiguous handle. --playlist-items and --no-playlist contradict each other,
        # so the item flag REPLACES it below.
        item_args = (
            ["--playlist-items", str(media.carousel_index)]
            if media.carousel_index is not None
            else ["--no-playlist"]
        )
        if format_ is MediaFormat.IMAGE:
            # Fetch the image URL directly (no format selector / no merge). The URL was
            # stashed on the IMAGE option at extraction time. Images are tiny — no bar.
            image_url = _selected_image_url(media)
            if not image_url:
                raise ExtractionFailedError("No image URL to download.")
            args = [self._bin, *item_args, "--no-warnings", "-o", out_template, image_url]
            await self._run(args, timeout_s=self._download_timeout)
        else:
            selector = _format_selector(media, format_, quality)
            base = [self._bin, "-f", selector, *item_args, "--no-warnings"]
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
                base, tail, dest, stem, media.platform, size, progress_cb
            )
        produced = sorted(dest.glob(f"{stem}.*"), key=lambda p: p.stat().st_size)
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
            async with self._cookie_session(platform, endpoint) as session:
                await self._invoke_download([*args, *tail], progress_cb, session.env)

        await self._run_egress_plan(platform, size_bytes, run)

    async def _invoke_download(
        self,
        args: list[str],
        progress_cb: DownloadProgress | None,
        env: dict[str, str] | None = None,
    ) -> None:
        if progress_cb is not None:
            await self._run_with_progress(
                args, timeout_s=self._download_timeout, progress_cb=progress_cb, env=env
            )
        else:
            await self._run(args, timeout_s=self._download_timeout, env=env)

    async def health_check(self) -> ProviderHealth:
        try:
            await self._run([self._bin, "--version"], timeout_s=_DEFAULT_HEALTH_TIMEOUT)
        except Exception:
            return ProviderHealth.UNAVAILABLE
        return ProviderHealth.OK

    # --- subprocess + error mapping ---------------------------------------
    async def _run(
        self, args: list[str], *, timeout_s: float, env: dict[str, str] | None = None
    ) -> tuple[bytes, bytes]:
        """Run yt-dlp to completion → ``(stdout, stderr)``; maps non-zero exits to
        domain errors. stderr is returned even on success — with
        ``--ignore-no-formats-error`` the reason an extraction produced no formats
        exists only there."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
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
            # Carry the raw stderr on the exception: the cookie pool classifies from it,
            # and the mapped message alone would lose the detail it needs.
            error.provider_stderr = decoded  # type: ignore[attr-defined]
            raise error
        return stdout, stderr

    async def _run_with_progress(
        self,
        args: list[str],
        *,
        timeout_s: float,
        progress_cb: DownloadProgress,
        env: dict[str, str] | None = None,
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
                env=env,
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


def _output_stem(media: MediaInfo) -> str:
    """Filesystem-safe stem for a download. Carousel ids carry a "#<n>" suffix."""
    return media.video_id.replace("#", "_")


class _NeedsOwnExtractionError(Exception):
    """Control flow: this entry must be extracted on its own url, not flattened."""

    def __init__(self, url: str, index: int) -> None:
        super().__init__(url)
        self.url = url
        self.index = index


def _is_playlist_url(url: str) -> bool:
    """A url whose primary subject is a LIST rather than one video.

    ``watch?v=…&list=…`` is deliberately excluded: the user asked for that video, and
    --no-playlist is what keeps it from expanding into the whole list.
    """
    lowered = url.lower()
    if "/playlist?" in lowered or ("list=" in lowered and "watch?" not in lowered):
        return True
    return any(marker in lowered for marker in ("/channel/", "/@", "/c/", "/user/"))


def _entry_own_url(entry: dict[str, Any]) -> str | None:
    """The entry's own page url, when it is a separately addressable video."""
    for key in ("webpage_url", "url"):
        value = entry.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    entry_id = entry.get("id")
    if entry.get("ie_key") == "Youtube" and entry_id:
        return f"https://www.youtube.com/watch?v={entry_id}"
    return None


def _entry_options(entry: dict[str, Any]) -> list[MediaFormatOption]:
    """The options a carousel entry would actually yield, via the normal parser.

    Deriving the picker label from the entry's RAW format heights was misleading: the
    raw list advertised 1440p while _parse_formats (which builds what the user can
    really choose) topped out at 480p, so the button promised a quality that was not
    on the next screen. Same parser here means the label cannot drift from reality.
    """
    return _parse_formats(entry.get("formats") or [], _opt_int(entry.get("duration")))


def _entry_kind(entry: dict[str, Any]) -> MediaFormat:
    """The item's dominant media type, from the options it actually yields.

    Derived, never hardcoded per platform: video wins over audio-only, and anything
    with no playable stream falls back to IMAGE (a photo slide). A new extractor that
    returns some novel shape therefore still lands somewhere sensible.
    """
    options = _entry_options(entry)
    if any(o.format is MediaFormat.VIDEO for o in options):
        return MediaFormat.VIDEO
    if any(o.format is MediaFormat.AUDIO for o in options):
        return MediaFormat.AUDIO
    # A flat playlist entry has no formats at all to infer from, but it does have its
    # own video url — it is a video we simply have not extracted yet. Without this it
    # fell through to IMAGE and every playlist rendered as a wall of "Download Image".
    if _entry_own_url(entry):
        return MediaFormat.VIDEO
    return MediaFormat.IMAGE


def _entry_has_audio(entry: dict[str, Any]) -> bool:
    """Whether an audio track is obtainable for this item.

    True when the item yields an AUDIO option — which covers both a separate audio
    stream (YouTube) and a muxed stream we can extract from (TikTok). False when every
    format is video-only, as Instagram reports for anonymous carousel items: yt-dlp's
    own -F table marks all 11 of them "video only", and a download confirms no audio
    stream in the file. Offering audio there is a dead end.
    """
    return any(o.format is MediaFormat.AUDIO for o in _entry_options(entry))


def _entry_thumbnail(entry: dict[str, Any]) -> str | None:
    """Best preview for a gallery item, in the Owner's stated priority order:

    1. the original image (a photo slide IS its own preview — highest fidelity)
    2. the video thumbnail yt-dlp singled out (``thumbnail``)
    3. the largest extracted thumbnail from the ``thumbnails`` list
    4. the post's artwork, applied by the caller as a last resort

    An empty preview is the thing to avoid: the gallery is a photo message, and a
    message that starts without one can never become a photo message later.
    """
    if _entry_kind(entry) is MediaFormat.IMAGE:
        if image := _best_image_url(entry):
            return image
    if thumb := entry.get("thumbnail"):
        return str(thumb)
    return _best_image_url(entry)


def _best_entry_height(entry: dict[str, Any]) -> int | None:
    """Tallest video tier actually OFFERED for a carousel entry, for the button label."""
    heights = [
        h
        for o in _entry_options(entry)
        if o.format is MediaFormat.VIDEO
        and (m := _NOTE_TIER_RE.match(o.quality.value))
        and (h := int(m.group(1)))
    ]
    return max(heights) if heights else None


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
    if any(m in lowered for m in _AUTH_REQUIRED_MARKERS):
        return AuthRequiredError(f"This content requires a logged-in session.{suffix}")
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
                    bitrate_kbps=tbr,
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
            bitrate_kbps=row.bitrate_kbps,
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
    bitrate_kbps: float | None = None


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
    format's SHORTER edge to the nearest standard tier. Snapping to *nearest* (not a
    floor) is what fixes 4K on wide videos (3840x2026 → 2160p, not 1440p).

    The short edge is what names a video in every orientation — 1920x1080 and
    1080x1920 are both "1080p". Measuring the LONGER edge against a 16:9 ladder, as
    this used to, silently demoted every portrait video by one or two tiers, which is
    most of Instagram: 1080x1440 read as 720p, 720x960 as 480p, 540x720 as 360p. The
    tiers then collapsed together and the user was offered — and shown — a far worse
    stream than the source actually had.
    """
    if format_note:
        match = _NOTE_TIER_RE.search(format_note)
        if match:
            return _nearest_tier(int(match.group(1)), _TIER_BY_SHORT_EDGE)
    if width and height:
        # Both edges known: the SHORT edge names the tier in any orientation.
        return _nearest_tier(min(width, height), _TIER_BY_SHORT_EDGE)
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
