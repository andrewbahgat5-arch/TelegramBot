"""Root pytest configuration shared by every test collection root.

During Sprint 0 the tree contains no tests yet. pytest exits with code 5
("no tests collected"), which CI would treat as a failure. Until the first
real test lands, treat an empty collection as success. This hook becomes inert
the moment any test exists.
"""

from __future__ import annotations

import pytest


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    no_tests_collected = 5
    if exitstatus == no_tests_collected:
        session.exitstatus = 0
