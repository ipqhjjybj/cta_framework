"""
Logging configuration for the CTA backtesting framework.

Usage:
    from utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Backtest started")
"""
from __future__ import annotations

import logging
import sys
from typing import Optional


_FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"
_root_configured = False


def configure_root_logger(
    level: int = logging.INFO,
    stream=sys.stdout,
) -> None:
    """
    Configure the root logger once.  Subsequent calls are no-ops.
    Called automatically by get_logger() if not already set up.
    """
    global _root_configured
    if _root_configured:
        return

    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    _root_configured = True


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """
    Return a named logger, initialising the root logger if necessary.

    Args:
        name:  Typically __name__ of the calling module.
        level: Optional override for this specific logger's level.
    """
    configure_root_logger()
    logger = logging.getLogger(name)
    if level is not None:
        logger.setLevel(level)
    return logger
