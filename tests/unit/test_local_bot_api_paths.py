"""Regression tests for local Bot API file-path resolution.

Two production bugs are pinned here, both hit while adding a cookie through Telegram:

1. Our self-hosted Bot API runs in ``--local`` mode and does NOT serve files over HTTP,
   so downloads must read from disk (``is_local=True``).
2. Its ``getFile`` returns a path *relative* to the per-bot directory
   (``documents/file_2.txt``), which aiogram's local mode passes straight to ``open()``
   → ``FileNotFoundError``. It must be anchored under ``<root>/<token>/``.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from infrastructure.telegram.client import LocalBotApiPathWrapper

_ROOT = "/var/lib/telegram-bot-api"
_TOKEN = "8537944128:AAE9pLcmPhp0-YXSnlpqLNoH"


def _wrapper() -> LocalBotApiPathWrapper:
    return LocalBotApiPathWrapper(_ROOT, _TOKEN)


def test_relative_path_is_anchored_under_the_per_bot_directory() -> None:
    # THE bug: 'documents/file_2.txt' -> FileNotFoundError before this wrapper existed.
    resolved = _wrapper().to_local("documents/file_2.txt")
    assert PurePosixPath(resolved).as_posix() == f"{_ROOT}/{_TOKEN}/documents/file_2.txt"


def test_absolute_path_is_passed_through_unchanged() -> None:
    # Keeps working if a future server version returns absolute paths instead.
    absolute = f"{_ROOT}/{_TOKEN}/documents/file_2.txt"
    assert PurePosixPath(_wrapper().to_local(absolute)).as_posix() == absolute


def test_to_server_strips_the_root_again() -> None:
    absolute = f"{_ROOT}/{_TOKEN}/documents/file_2.txt"
    assert PurePosixPath(_wrapper().to_server(absolute)).as_posix() == "documents/file_2.txt"


def test_to_server_leaves_a_relative_path_alone() -> None:
    assert PurePosixPath(_wrapper().to_server("documents/file_2.txt")).as_posix() == (
        "documents/file_2.txt"
    )


def test_to_server_tolerates_a_path_outside_the_root() -> None:
    # Must not raise ValueError from relative_to on an unexpected layout.
    other = "/somewhere/else/file.txt"
    assert PurePosixPath(_wrapper().to_server(other)).as_posix() == other


def test_wrapper_is_posix_regardless_of_host_os() -> None:
    """The paths come from a Linux container; resolution must not depend on the OS the
    tests happen to run on (this failed first on Windows, where "/var/lib/..." is not
    considered absolute)."""
    resolved = _wrapper().to_local("documents/file_0.txt")
    assert str(resolved).startswith("/var/lib/telegram-bot-api/")
    assert "\\" not in str(resolved)
