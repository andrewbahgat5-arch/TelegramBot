"""Error classification (MASTER_PLAN 10.12: ``error_logs.error_type``).

Persisted as VARCHAR(30); every value below is <= 30 chars. Each leaf of the
domain exception hierarchy (MASTER_PLAN 15.4) maps to exactly one value here, so
``error_logs`` can be aggregated by ``error_type`` for the ``errors_total{type}``
metric (15.3). ``UNKNOWN`` is the fallback for anything uncategorized.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorType(StrEnum):
    # User-facing
    URL_NOT_SUPPORTED = "url_not_supported"
    FORMAT_NOT_AVAILABLE = "format_not_available"
    FILE_TOO_LARGE = "file_too_large"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    DAILY_LIMIT_EXCEEDED = "daily_limit_exceeded"
    COOLDOWN_ACTIVE = "cooldown_active"
    MAINTENANCE_MODE = "maintenance_mode"
    PERMISSION_DENIED = "permission_denied"
    # Download pipeline
    EXTRACTION_FAILED = "extraction_failed"
    DOWNLOAD_TIMEOUT = "download_timeout"
    FFMPEG_PROCESSING = "ffmpeg_processing"
    TELEGRAM_UPLOAD = "telegram_upload"
    # Internal / control flow
    DUPLICATE_DOWNLOAD = "duplicate_download"
    JOB_NOT_FOUND = "job_not_found"
    CACHED_FILE_EXPIRED = "cached_file_expired"
    # Cache
    CACHE_CONNECTION = "cache_connection"
    CACHE_SERIALIZATION = "cache_serialization"
    # Infrastructure
    DATABASE_CONNECTION = "database_connection"
    REDIS_CONNECTION = "redis_connection"
    # Fallback
    UNKNOWN = "unknown"
