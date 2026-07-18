"""Validate an uploaded cookies.txt before it is allowed into the pool (§10 step 3).

Pure and dependency-free. This is the cheap gate that runs before the expensive canary
extraction: it catches the "pasted the wrong export" case in milliseconds instead of
letting a useless file occupy a pool slot until someone notices downloads failing.

What it deliberately does NOT do: judge whether the session is *live*. Only the canary
can answer that, because a syntactically perfect export can still be a dead session.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Cookies that make a YouTube session a *logged-in* session. Google issues them in two
#: shapes depending on the export, so either family is accepted.
_CLASSIC_AUTH = {"SID", "HSID", "SSID", "APISID", "SAPISID"}
_SECURE_AUTH = {"__Secure-1PSID", "__Secure-3PSID", "__Secure-1PAPISID", "__Secure-3PAPISID"}

_MAX_BYTES = 1024 * 1024  # 1 MB — a real export is a few KB
_MIN_COOKIE_LINES = 5


@dataclass(frozen=True, slots=True)
class CookieValidation:
    ok: bool
    reason: str = ""
    cookie_count: int = 0
    names: frozenset[str] = frozenset()

    @property
    def is_logged_in(self) -> bool:
        return bool(self.names & _CLASSIC_AUTH) or bool(self.names & _SECURE_AUTH)


def validate_cookie_file(content: bytes) -> CookieValidation:
    """Check size, Netscape format and the presence of real authentication cookies."""
    if not content.strip():
        return CookieValidation(False, "The file is empty.")
    if len(content) > _MAX_BYTES:
        return CookieValidation(False, "That file is too large to be a cookie export.")

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return CookieValidation(False, "The file is not UTF-8 text — is it really cookies.txt?")

    names: set[str] = set()
    domains: set[str] = set()
    count = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # "#HttpOnly_" is a cookie line, not a comment — Google marks its auth cookies
        # HttpOnly, so skipping those would discard exactly what we are checking for.
        if line.startswith("#") and not line.startswith("#HttpOnly_"):
            continue
        fields = line.split("\t")
        if len(fields) < 7:
            continue
        count += 1
        domains.add(fields[0].removeprefix("#HttpOnly_").lstrip("."))
        names.add(fields[5])

    if count < _MIN_COOKIE_LINES:
        return CookieValidation(
            False,
            "That doesn't look like a Netscape cookie file "
            "(expected tab-separated cookie lines).",
            count,
            frozenset(names),
        )
    if not any("youtube.com" in d or "google.com" in d for d in domains):
        return CookieValidation(
            False, "No youtube.com cookies found in that file.", count, frozenset(names)
        )

    validation = CookieValidation(True, "", count, frozenset(names))
    if not validation.is_logged_in:
        return CookieValidation(
            False,
            "These cookies are not signed in — the session cookies (SID / __Secure-*PSID) "
            "are missing. Export again while logged in to YouTube.",
            count,
            frozenset(names),
        )
    return validation
