"""Smoke entry point (MASTER_PLAN Task 1.8).

Wires ``core/logging.py`` and emits a single structured log line, proving the
logging stack configures and renders end-to-end. Reads ``LOG_LEVEL`` / ``LOG_FORMAT``
directly from the environment (with the Section 13.2 defaults) so it runs without a
fully populated ``.env``.

    python -m core
"""

from __future__ import annotations

import os

from core.logging import bind_correlation_id, configure_logging, get_logger
from core.uuid7 import uuid7_str


def main() -> None:
    configure_logging(
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        log_format=os.environ.get("LOG_FORMAT", "json"),
    )
    bind_correlation_id(uuid7_str())
    log = get_logger("core.__main__")
    log.info("logging_smoke_ok", component="core", note="structured logging is wired")


if __name__ == "__main__":
    main()
