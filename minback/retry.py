"""Retry with exponential backoff."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

log = logging.getLogger(__name__)


def retry[T](
    fn: Callable[[], T], attempts: int, delay: float, what: str, sleep: Callable[[float], None] = time.sleep
) -> T:
    """Call fn up to `attempts` times, waiting delay, 2*delay, 4*delay... between tries."""
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:
            if attempt == attempts:
                log.error("%s failed after %d attempt(s): %s", what, attempts, e)
                raise
            wait = delay * 2 ** (attempt - 1)
            log.warning("%s failed (attempt %d/%d): %s; retrying in %.0fs", what, attempt, attempts, e, wait)
            sleep(wait)
    raise AssertionError("unreachable")
