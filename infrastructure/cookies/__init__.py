"""Cookie material storage + persistence adapters (DESIGN_COOKIE_POOL.md §5, §14)."""

from __future__ import annotations

from infrastructure.cookies.local_store import InvalidCookieLabelError, LocalCookieStore
from infrastructure.cookies.repository_adapter import CookieRepositoryAdapter

__all__ = ["CookieRepositoryAdapter", "InvalidCookieLabelError", "LocalCookieStore"]
