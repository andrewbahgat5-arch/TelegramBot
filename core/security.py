"""Security helpers (MASTER_PLAN Task 11.1, Section 14).

Pure, dependency-free crypto helpers. Used by the environment safety rules
(``core.environment``) and the simulation / e2e production-credential guards
(Section 25.6, 25.15.10).
"""

from __future__ import annotations

import hashlib


def token_fingerprint(token: str) -> str:
    """Return a stable SHA-256 hex fingerprint of a bot token.

    A one-way digest: it identifies a token (e.g. to detect the production bot in
    a test deployment, D-060) without storing or exposing the secret itself, so
    the fingerprint is safe to keep in config and ``.env.example`` (Hard Rule 6).
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
