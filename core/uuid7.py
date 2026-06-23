"""UUIDv7 generator (MASTER_PLAN D-013, D-023).

Time-ordered UUIDs (RFC 9562 version 7) used for ``jobs.id`` and correlation IDs.
Sequential values keep B-tree inserts append-mostly at the project's write rate,
avoiding index bloat that UUIDv4 would cause.

A pure ~80-line implementation with no third-party dependency (D-023). Generation
is monotonic *within a process*: values are strictly increasing even when many are
requested inside the same millisecond, and a backwards clock step cannot produce a
smaller value than one already issued.

Layout (128 bits, RFC 9562 §5.7):
    unix_ts_ms : 48 bits   millisecond timestamp
    version    :  4 bits   = 0b0111
    rand_a     : 12 bits   per-millisecond monotonic counter (seeded randomly)
    variant    :  2 bits   = 0b10
    rand_b     : 62 bits   random
"""

from __future__ import annotations

import secrets
import threading
import time
import uuid
from typing import Final

_VERSION: Final[int] = 0x7
_VARIANT: Final[int] = 0b10
_COUNTER_BITS: Final[int] = 12
_COUNTER_MAX: Final[int] = (1 << _COUNTER_BITS) - 1
_RAND_B_BITS: Final[int] = 62
_TS_MASK: Final[int] = (1 << 48) - 1

_lock = threading.Lock()
_last_ms: int = -1
_counter: int = 0


def uuid7() -> uuid.UUID:
    """Return a new time-ordered UUIDv7, monotonic within this process."""
    global _last_ms, _counter

    with _lock:
        now_ms = time.time_ns() // 1_000_000

        if now_ms > _last_ms:
            # New (later) millisecond: adopt it and seed a fresh random counter,
            # leaving headroom so we can increment within the millisecond.
            _last_ms = now_ms
            _counter = secrets.randbits(_COUNTER_BITS) >> 1
        else:
            # Same millisecond, or the clock moved backwards. Either way keep the
            # last issued timestamp and increment the counter for monotonicity.
            _counter += 1
            if _counter > _COUNTER_MAX:
                # Counter exhausted: borrow from the next millisecond.
                _last_ms += 1
                _counter = 0

        ms = _last_ms
        counter = _counter
        rand_b = secrets.randbits(_RAND_B_BITS)

    value = (ms & _TS_MASK) << 80
    value |= _VERSION << 76
    value |= (counter & _COUNTER_MAX) << 64
    value |= _VARIANT << 62
    value |= rand_b
    return uuid.UUID(int=value)


def uuid7_str() -> str:
    """Convenience: a new UUIDv7 rendered as its canonical string."""
    return str(uuid7())
