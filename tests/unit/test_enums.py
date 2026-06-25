"""Unit tests for domain enums (MASTER_PLAN 9.4)."""

from __future__ import annotations

from domain.enums import AdType, ErrorType, JobStatus, MediaFormat, Quality, UserRole


def test_jobstatus_values_are_stable() -> None:
    assert JobStatus.QUEUED.value == "queued"
    assert str(JobStatus.PROCESSING) == "processing"
    assert {s.value for s in JobStatus} == {
        "created",
        "queued",
        "processing",
        "completed",
        "failed",
        "retry_queued",
        "permanently_failed",
        "timed_out",
        "cancelled",
    }


def test_jobstatus_terminal_set() -> None:
    terminal = {s for s in JobStatus if s.is_terminal}
    assert terminal == {
        JobStatus.COMPLETED,
        JobStatus.PERMANENTLY_FAILED,
        JobStatus.CANCELLED,
    }
    # TIMED_OUT is transient, not terminal (Section 12.3).
    assert not JobStatus.TIMED_OUT.is_terminal
    assert not JobStatus.PROCESSING.is_terminal


def test_user_role_staff() -> None:
    assert UserRole.OWNER.is_staff
    assert UserRole.MODERATOR.is_staff
    assert not UserRole.USER.is_staff
    assert {r.value for r in UserRole} == {"owner", "moderator", "user"}


def test_media_format_values() -> None:
    assert {f.value for f in MediaFormat} == {"video", "audio"}


def test_quality_contains_resolution_ladder_and_audio() -> None:
    values = {q.value for q in Quality}
    assert {"144p", "360p", "720p", "1080p", "2160p"} <= values
    assert "audio" in values
    assert "best" in values


def test_ad_type_values() -> None:
    assert {a.value for a in AdType} == {
        "text",
        "photo",
        "video",
        "animation",
        "document",
        "audio",
        "album",
    }


def test_error_type_values_fit_column_width() -> None:
    # error_logs.error_type is VARCHAR(30).
    for error_type in ErrorType:
        assert len(error_type.value) <= 30
    assert ErrorType.UNKNOWN.value == "unknown"
