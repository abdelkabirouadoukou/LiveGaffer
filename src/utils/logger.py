"""
Centralized logging configuration using loguru.

Import `get_logger(__name__)` anywhere in the codebase to get a consistently
formatted, leveled logger instead of sprinkling `print()` calls.
"""

from __future__ import annotations

import sys
from functools import lru_cache

from loguru import logger as _loguru_logger

from config.settings import get_settings

_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{extra[component]}</cyan> | "
    "<level>{message}</level>"
)


@lru_cache(maxsize=1)
def _configure_root_logger() -> None:
    """Configure loguru sinks exactly once per process."""
    settings = get_settings()
    _loguru_logger.remove()  # drop loguru's default handler
    _loguru_logger.add(
        sys.stderr,
        format=_LOG_FORMAT,
        level=settings.log_level.value,
        colorize=True,
        backtrace=False,
        diagnose=False,
    )


def get_logger(component: str):
    """
    Return a logger bound to `component` (typically `__name__`).

    Example:
        log = get_logger(__name__)
        log.info("Fetched fixture {}", fixture_id)
    """
    _configure_root_logger()
    return _loguru_logger.bind(component=component)
