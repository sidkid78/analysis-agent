"""Logging setup. Operations log to ``smart-dev-env.log`` for audit/debugging.

Stdout is reserved for the MCP stdio transport, so file logging only (a stderr
handler is added when ``SMART_DEV_DEBUG`` is set).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

_LOG_FILE = Path(os.getenv("SMART_DEV_LOG") or (Path.cwd() / "smart-dev-env.log"))
_configured = False


def get_logger(name: str = "smart_dev") -> logging.Logger:
    global _configured
    logger = logging.getLogger(name)
    if not _configured:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        try:
            fh = logging.FileHandler(_LOG_FILE, encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except OSError:
            pass  # read-only fs — skip file logging
        if os.getenv("SMART_DEV_DEBUG"):
            sh = logging.StreamHandler()  # stderr
            sh.setFormatter(fmt)
            logger.addHandler(sh)
        _configured = True
    return logger
