"""Unit tests for ErrorLogService (the error_logs write path)."""

from __future__ import annotations

import uuid

from domain.exceptions import VideoUnavailableError
from services.error_log_service import ErrorLogService


class _FakeErrorLogRepo:
    def __init__(self, *, fail: bool = False) -> None:
        self.rows: list[dict[str, object]] = []
        self._fail = fail

    async def record(self, **kwargs: object) -> None:
        if self._fail:
            raise RuntimeError("db down")
        self.rows.append(kwargs)


async def test_domain_error_uses_hierarchy_error_type_and_correlation() -> None:
    repo = _FakeErrorLogRepo()
    service = ErrorLogService(repo)  # type: ignore[arg-type]
    correlation = str(uuid.uuid4())
    await service.record_failure(
        VideoUnavailableError("wall"),
        context="analyze youtube youtu.be c615f378dd02",
        user_id=7,
        correlation_id=correlation,
    )
    assert len(repo.rows) == 1
    row = repo.rows[0]
    assert row["error_type"] == "video_unavailable"  # Section 15.4 value, not class name
    assert row["user_id"] == 7
    assert row["correlation_id"] == uuid.UUID(correlation)
    assert "analyze youtube" in str(row["message"])
    assert row["traceback_text"] is None


async def test_non_domain_error_uses_class_name_and_captures_traceback() -> None:
    repo = _FakeErrorLogRepo()
    service = ErrorLogService(repo)  # type: ignore[arg-type]
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        await service.record_failure(exc, context="analyze", with_traceback=True)
    row = repo.rows[0]
    assert row["error_type"] == "RuntimeError"
    assert "boom" in str(row["traceback_text"])


async def test_unparseable_correlation_id_becomes_none() -> None:
    repo = _FakeErrorLogRepo()
    service = ErrorLogService(repo)  # type: ignore[arg-type]
    await service.record_failure(RuntimeError("x"), context="c", correlation_id="not-a-uuid")
    assert repo.rows[0]["correlation_id"] is None


async def test_repo_failure_is_swallowed() -> None:
    # A failure to log a failure must never break the user-facing flow.
    service = ErrorLogService(_FakeErrorLogRepo(fail=True))  # type: ignore[arg-type]
    await service.record_failure(RuntimeError("x"), context="c")  # must not raise
