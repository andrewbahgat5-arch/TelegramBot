"""Packed-arg helpers for paginated callback data.

A signed callback carries one small int ``arg``.  When a screen needs both a
*filter index* (language bucket, format filter, …) and a *page number*, we
encode them as ``arg = filter_index * 100 + page`` and decode with ``divmod``.
Page must be < 100; filter index must be a small non-negative int.

Shared by history (Phase 1.3) and broadcast list (Phase 3).
"""

from __future__ import annotations


def encode_filter_page(filter_index: int, page: int) -> int:
    return filter_index * 100 + page


def decode_filter_page(arg: int) -> tuple[int, int]:
    filter_index, page = divmod(arg, 100)
    return filter_index, page
