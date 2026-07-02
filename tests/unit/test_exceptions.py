"""Unit tests for the domain exception hierarchy (MASTER_PLAN 15.4)."""

from __future__ import annotations

import pytest

from core.i18n import translate
from domain.enums import ErrorType
from domain.exceptions import (
    AppError,
    CacheConnectionError,
    CacheError,
    CooldownActiveError,
    DailyLimitExceededError,
    DatabaseConnectionError,
    DownloadError,
    DuplicateDownloadError,
    ExtractionFailedError,
    FileTooLargeError,
    FormatNotAvailableError,
    InfrastructureError,
    MaintenanceModeError,
    PermissionDeniedError,
    RateLimitExceededError,
    URLNotSupportedError,
    UserFacingError,
)


def test_hierarchy_relationships() -> None:
    assert issubclass(URLNotSupportedError, UserFacingError)
    assert issubclass(UserFacingError, AppError)
    assert issubclass(ExtractionFailedError, DownloadError)
    assert issubclass(CacheConnectionError, CacheError)
    assert issubclass(DatabaseConnectionError, InfrastructureError)


def test_default_error_type_is_unknown() -> None:
    assert AppError().error_type is ErrorType.UNKNOWN


def test_leaf_error_type_mapping() -> None:
    assert URLNotSupportedError().error_type is ErrorType.URL_NOT_SUPPORTED
    assert ExtractionFailedError().error_type is ErrorType.EXTRACTION_FAILED
    assert DatabaseConnectionError().error_type is ErrorType.DATABASE_CONNECTION


def test_message_defaults_to_class_name() -> None:
    assert URLNotSupportedError().message == "URLNotSupportedError"
    assert str(URLNotSupportedError("bad url")) == "bad url"


def test_duplicate_download_carries_job_id() -> None:
    err = DuplicateDownloadError(job_id="job-123")
    assert err.job_id == "job-123"
    assert err.error_type is ErrorType.DUPLICATE_DOWNLOAD


def test_app_errors_are_raisable() -> None:
    with pytest.raises(AppError):
        raise CacheConnectionError("redis down")


def test_each_concrete_leaf_has_distinct_error_type() -> None:
    leaves = [
        cls
        for cls in _all_subclasses(AppError)
        if "error_type" in vars(cls)  # leaf sets its own error_type
    ]
    error_types = [cls.error_type for cls in leaves]
    assert len(error_types) == len(set(error_types)), "error_type values must be unique"


def _all_subclasses(root: type[AppError]) -> list[type[AppError]]:
    found: list[type[AppError]] = []
    for sub in root.__subclasses__():
        found.append(sub)
        found.extend(_all_subclasses(sub))
    return found


# --- i18n (Sprint 11.5) -----------------------------------------------------
def test_translation_key_derives_from_error_type() -> None:
    assert URLNotSupportedError().translation_key == "errors.url_not_supported"
    assert FileTooLargeError().translation_key == "errors.file_too_large"


@pytest.mark.parametrize(
    "exc",
    [
        URLNotSupportedError(),
        FormatNotAvailableError(),
        FileTooLargeError(),
        RateLimitExceededError(),
        DailyLimitExceededError(),
        CooldownActiveError(),
        MaintenanceModeError(),
        PermissionDeniedError(),
    ],
)
def test_every_user_facing_error_resolves_a_real_catalog_key(exc: UserFacingError) -> None:
    """Catches drift: a renamed/added ``UserFacingError`` subclass without a matching
    ``errors.*`` catalog entry silently falls back to the raw key at runtime instead of
    failing a test — this asserts the fallback path is never actually exercised."""
    resolved = translate(exc.translation_key, "en")
    assert resolved != exc.translation_key
