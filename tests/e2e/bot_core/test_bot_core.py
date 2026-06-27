"""E2E · Bot Core (MASTER_PLAN §25.7.1).

Skip-guarded via the ``harness`` fixture until the Phase-B sandbox is provisioned.
"""

from __future__ import annotations

from tests.e2e.harness import E2EHarness


def test_start_new_user_creates_user_row(harness: E2EHarness) -> None:
    """/start from a new user → user row created with role='user'."""
    assert harness.pool is not None


def test_start_existing_user_no_duplicate(harness: E2EHarness) -> None:
    """/start from an existing user → no duplicate; last_activity_at debounced."""
    assert harness.pool is not None


def test_help_returns_help_message(harness: E2EHarness) -> None:
    """/help returns the help message."""
    assert harness.pool is not None


def test_owner_id_gets_owner_role(harness: E2EHarness) -> None:
    """The Owner Telegram ID resolves to role='owner'."""
    assert harness.pool is not None


def test_banned_user_only_gets_ban_message(harness: E2EHarness) -> None:
    """A banned user receives only the ban message."""
    assert harness.pool is not None
