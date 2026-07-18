"""Unit tests for the uploaded-cookie validator (DESIGN_COOKIE_POOL.md §10)."""

from __future__ import annotations

from services.cookie_validator import validate_cookie_file

_HEADER = "# Netscape HTTP Cookie File\n"


def _line(name: str, domain: str = ".youtube.com", value: str = "x") -> str:
    return f"{domain}\tTRUE\t/\tTRUE\t1799790689\t{name}\t{value}\n"


def _logged_in_export() -> bytes:
    body = "".join(
        _line(n) for n in ("SID", "HSID", "SSID", "APISID", "SAPISID", "PREF", "YSC")
    )
    return (_HEADER + body).encode()


def test_accepts_a_real_logged_in_export() -> None:
    result = validate_cookie_file(_logged_in_export())
    assert result.ok is True
    assert result.is_logged_in is True
    assert result.cookie_count == 7


def test_accepts_the_secure_psid_family() -> None:
    # Some exports carry __Secure-*PSID instead of the classic SID set.
    body = "".join(
        _line(n)
        for n in ("__Secure-1PSID", "__Secure-3PSID", "PREF", "YSC", "VISITOR_INFO1_LIVE")
    )
    assert validate_cookie_file((_HEADER + body).encode()).ok is True


def test_counts_httponly_lines_as_cookies() -> None:
    # Google marks its auth cookies HttpOnly; treating those as comments would discard
    # exactly what we are checking for.
    body = "".join(
        _line(n, domain="#HttpOnly_.youtube.com")
        for n in ("SID", "HSID", "SSID", "APISID", "SAPISID")
    )
    result = validate_cookie_file((_HEADER + body).encode())
    assert result.ok is True
    assert result.cookie_count == 5


def test_rejects_an_empty_file() -> None:
    assert validate_cookie_file(b"   ").ok is False


def test_rejects_non_utf8() -> None:
    assert validate_cookie_file(b"\xff\xfe\x00binary").ok is False


def test_rejects_something_that_is_not_a_cookie_file() -> None:
    result = validate_cookie_file(b"just some pasted text\nand another line\n")
    assert result.ok is False
    assert "Netscape" in result.reason


def test_rejects_cookies_for_the_wrong_site() -> None:
    body = "".join(_line(n, domain=".example.com") for n in ("a", "b", "c", "d", "e"))
    result = validate_cookie_file((_HEADER + body).encode())
    assert result.ok is False
    assert "youtube.com" in result.reason


def test_rejects_a_logged_out_export_with_a_useful_message() -> None:
    # The most likely admin mistake: exporting without being signed in.
    body = "".join(
        _line(n) for n in ("PREF", "YSC", "VISITOR_INFO1_LIVE", "GPS", "SOCS", "wide")
    )
    result = validate_cookie_file((_HEADER + body).encode())
    assert result.ok is False
    assert result.is_logged_in is False
    assert "not signed in" in result.reason


def test_rejects_an_implausibly_large_file() -> None:
    assert validate_cookie_file(b"x" * (2 * 1024 * 1024)).ok is False
