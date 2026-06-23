"""URL parsing helpers (MASTER_PLAN 16.1, 12.6.3).

Pure, framework-free functions shared by the service layer (``URLAnalyzerService``
extracts ``(platform, video_id)`` and normalizes) and the infrastructure layer
(``DownloaderRegistry`` detects the platform) — a 3+-layer helper, so it lives in
``core`` (Section 7.1). ``core`` is a leaf: no project imports.

Platform detection is best-effort. yt-dlp (the sole V1 provider) supports ``"*"``,
so an unrecognised host is classified ``"generic"`` and still attempted; the
provider, not this module, has the final say on whether a URL is supported. The
approved platform allowlist is OQ-8 (still open) — detection here does not gate.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse, urlunparse

# Platform id → (host-substring matchers, ordered video-id extractors).
_YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")
_PLATFORM_HOSTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("youtube", _YOUTUBE_HOSTS),
    ("tiktok", ("tiktok.com",)),
    ("instagram", ("instagram.com",)),
    ("twitter", ("twitter.com", "x.com")),
    ("facebook", ("facebook.com", "fb.watch")),
)

_VIDEO_ID_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "youtube": (
        re.compile(r"[?&]v=([\w-]{6,})"),
        re.compile(r"youtu\.be/([\w-]{6,})"),
        re.compile(r"/shorts/([\w-]{6,})"),
        re.compile(r"/embed/([\w-]{6,})"),
    ),
    "tiktok": (re.compile(r"/video/(\d+)"), re.compile(r"tiktok\.com/(?:v|t)/(\w+)")),
    "instagram": (re.compile(r"/(?:p|reel|tv)/([\w-]+)"),),
    "twitter": (re.compile(r"/status/(\d+)"),),
    "facebook": (re.compile(r"/videos/(\d+)"), re.compile(r"fb\.watch/(\w+)")),
}

_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)


def is_valid_url(url: str) -> bool:
    """True when ``url`` is a syntactically valid http(s) URL with a host."""
    candidate = url.strip()
    if not _SCHEME_RE.match(candidate):
        return False
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return False
    return bool(parsed.netloc)


def normalize_url(url: str) -> str:
    """Canonicalise: trim, lowercase scheme+host, drop the fragment."""
    parsed = urlparse(url.strip())
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            parsed.params,
            parsed.query,
            "",  # fragment dropped
        )
    )


def detect_platform(url: str) -> str:
    """Classify the URL's platform, or ``"generic"`` when unrecognised."""
    host = urlparse(url.strip()).netloc.lower()
    for platform, hosts in _PLATFORM_HOSTS:
        if any(h in host for h in hosts):
            return platform
    return "generic"


def extract_video_id(url: str, platform: str) -> str:
    """Best-effort stable content id for ``(platform, video_id)`` keying.

    Falls back to a deterministic hash of the normalized URL so every URL yields a
    stable, ≤255-char id even when no platform-specific pattern matches.
    """
    normalized = normalize_url(url)
    for pattern in _VIDEO_ID_PATTERNS.get(platform, ()):
        match = pattern.search(normalized)
        if match:
            return match.group(1)
    return hashlib.sha1(normalized.encode(), usedforsecurity=False).hexdigest()
