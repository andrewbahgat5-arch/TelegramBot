"""Domain exception hierarchy (MASTER_PLAN 15.4, LOCKED).

The tree below mirrors Section 15.4 exactly. Reordering or renaming existing
types is a breaking change (Section 9.4). Every concrete exception carries an
``error_type`` (``domain.enums.ErrorType``) so persistence into ``error_logs``
and the ``errors_total{type}`` metric are consistent and centralized.

``UserFacingError`` subclasses are safe to surface to the end user (their message
is user-appropriate). All other branches are internal and must be translated to a
generic, localized message before reaching a user.
"""

from __future__ import annotations

from domain.enums import ErrorType


class AppError(Exception):
    """Root of every application-specific error."""

    error_type: ErrorType = ErrorType.UNKNOWN

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.__class__.__name__
        super().__init__(self.message)


# --- User-facing ----------------------------------------------------------
class UserFacingError(AppError):
    """Base for errors whose message is safe to show the user verbatim."""


class URLNotSupportedError(UserFacingError):
    error_type = ErrorType.URL_NOT_SUPPORTED


class FormatNotAvailableError(UserFacingError):
    error_type = ErrorType.FORMAT_NOT_AVAILABLE


class FileTooLargeError(UserFacingError):
    error_type = ErrorType.FILE_TOO_LARGE


class RateLimitExceededError(UserFacingError):
    error_type = ErrorType.RATE_LIMIT_EXCEEDED


class DailyLimitExceededError(UserFacingError):
    error_type = ErrorType.DAILY_LIMIT_EXCEEDED


class CooldownActiveError(UserFacingError):
    error_type = ErrorType.COOLDOWN_ACTIVE


class MaintenanceModeError(UserFacingError):
    error_type = ErrorType.MAINTENANCE_MODE


class PermissionDeniedError(UserFacingError):
    error_type = ErrorType.PERMISSION_DENIED


# --- Download pipeline ----------------------------------------------------
class DownloadError(AppError):
    """Base for failures in the download/transcode/upload pipeline."""


class ExtractionFailedError(DownloadError):
    error_type = ErrorType.EXTRACTION_FAILED


class DownloadTimeoutError(DownloadError):
    error_type = ErrorType.DOWNLOAD_TIMEOUT


class FFmpegProcessingError(DownloadError):
    error_type = ErrorType.FFMPEG_PROCESSING


class TelegramUploadError(DownloadError):
    error_type = ErrorType.TELEGRAM_UPLOAD


# --- Internal / control flow ----------------------------------------------
class DuplicateDownloadError(AppError):
    """Raised internally when a duplicate active request is detected.

    Drives the fan-out path (MASTER_PLAN 12.4): the caller attaches the user to
    the in-flight job identified by ``job_id`` rather than starting a new one.
    """

    error_type = ErrorType.DUPLICATE_DOWNLOAD

    def __init__(self, job_id: str, message: str | None = None) -> None:
        super().__init__(message)
        self.job_id = job_id


class JobNotFoundError(AppError):
    error_type = ErrorType.JOB_NOT_FOUND


# --- Cache ----------------------------------------------------------------
class CacheError(AppError):
    """Base for Redis cache failures."""


class CacheConnectionError(CacheError):
    error_type = ErrorType.CACHE_CONNECTION


class CacheSerializationError(CacheError):
    error_type = ErrorType.CACHE_SERIALIZATION


# --- Infrastructure -------------------------------------------------------
class InfrastructureError(AppError):
    """Base for backing-store connectivity failures."""


class DatabaseConnectionError(InfrastructureError):
    error_type = ErrorType.DATABASE_CONNECTION


class RedisConnectionError(InfrastructureError):
    error_type = ErrorType.REDIS_CONNECTION


__all__ = [
    "AppError",
    "CacheConnectionError",
    "CacheError",
    "CacheSerializationError",
    "CooldownActiveError",
    "DailyLimitExceededError",
    "DatabaseConnectionError",
    "DownloadError",
    "DownloadTimeoutError",
    "DuplicateDownloadError",
    "ExtractionFailedError",
    "FFmpegProcessingError",
    "FileTooLargeError",
    "FormatNotAvailableError",
    "InfrastructureError",
    "JobNotFoundError",
    "MaintenanceModeError",
    "PermissionDeniedError",
    "RateLimitExceededError",
    "RedisConnectionError",
    "TelegramUploadError",
    "URLNotSupportedError",
    "UserFacingError",
]
