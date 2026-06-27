"""Unit tests for core/security.py (MASTER_PLAN Task 11.1, Section 14)."""

from __future__ import annotations

import hashlib

from core.security import token_fingerprint


def test_token_fingerprint_matches_sha256() -> None:
    token = "123456:ABC-def_ghi"
    expected = hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert token_fingerprint(token) == expected


def test_token_fingerprint_is_stable() -> None:
    token = "bot-token-test-XXXX"
    assert token_fingerprint(token) == token_fingerprint(token)


def test_token_fingerprint_differs_per_token() -> None:
    assert token_fingerprint("token-a") != token_fingerprint("token-b")


def test_token_fingerprint_does_not_contain_token() -> None:
    # The digest is one-way: the plaintext must not be recoverable from it.
    token = "super-secret-prod-token"
    assert token not in token_fingerprint(token)
