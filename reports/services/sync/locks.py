"""Per-report sync locks to prevent parallel duplicate syncs."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from django.core.cache import cache

logger = logging.getLogger(__name__)

LOCK_TTL_SECONDS = 60 * 30  # 30 minutes max lock


@contextmanager
def report_sync_lock(report_key: str) -> Iterator[bool]:
    """
    Yields True if lock acquired, False if another sync holds the lock.

    Uses Django cache (locmem/redis). Safe for single-process APScheduler;
    for multi-worker, configure Redis cache backend.
    """
    lock_key = f"kara:sync:lock:{report_key}"
    acquired = cache.add(lock_key, "1", timeout=LOCK_TTL_SECONDS)
    if not acquired:
        logger.warning("Sync lock busy for %s", report_key)
        yield False
        return
    try:
        yield True
    finally:
        cache.delete(lock_key)
