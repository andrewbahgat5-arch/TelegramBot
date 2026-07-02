"""Root pytest configuration shared by every test collection root.

During Sprint 0 the tree contains no tests yet. pytest exits with code 5
("no tests collected"), which CI would treat as a failure. Until the first
real test lands, treat an empty collection as success. This hook becomes inert
the moment any test exists.
"""

from __future__ import annotations

import pytest

from core import i18n


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    no_tests_collected = 5
    if exitstatus == no_tests_collected:
        session.exitstatus = 0


@pytest.fixture(autouse=True)
def _configure_i18n() -> None:
    """Every test gets a working ``core.i18n`` (Sprint 11.5) against the real
    ``core/locales/*.json`` catalogs, English default — mirrors how the bot
    process configures it once at startup. Tests targeting catalog validation
    itself call ``i18n.configure()`` again with a fixture directory.
    """
    i18n.configure("en")
