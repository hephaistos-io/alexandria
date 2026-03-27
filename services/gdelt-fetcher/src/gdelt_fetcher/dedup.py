"""Key deduplication backends for the GDELT fetch loop.

Two implementations:
- RedisSeenUrls: persists seen keys in Redis with TTL. Survives restarts.
- InMemorySeenUrls: bounded OrderedDict, used when REDIS_URL is not set.
"""

import logging
from collections import OrderedDict
from typing import Protocol

import redis

logger = logging.getLogger(__name__)

# Per-key TTL: 2 days. GDELT events are unique by GlobalEventID and won't
# reappear in future exports, but we keep a short TTL as a safety net.
_DEDUP_TTL_SECONDS = 2 * 24 * 60 * 60

# Upper bound for in-memory fallback. Each 15-minute GDELT export has ~50-200
# conflict events, so 50K covers many cycles.
MAX_SEEN_KEYS = 50_000


class SeenUrls(Protocol):
    """Interface for deduplication backends."""

    def contains(self, url: str) -> bool: ...
    def add(self, url: str) -> None: ...


class RedisSeenUrls:
    """Dedup backed by individual Redis keys with TTL."""

    def __init__(self, redis_url: str) -> None:
        self._client = redis.from_url(redis_url)
        self._prefix = "seen:gdelt:"
        self._ttl = _DEDUP_TTL_SECONDS

        try:
            self._client.ping()
            logger.info("Redis dedup enabled (prefix=%s, ttl=%ds)", self._prefix, self._ttl)
        except redis.RedisError:
            logger.error("Redis ping failed at startup — dedup writes may fail. Check REDIS_URL.")

    def _key(self, key: str) -> str:
        return self._prefix + key

    def contains(self, url: str) -> bool:
        try:
            return bool(self._client.exists(self._key(url)))
        except redis.RedisError:
            logger.warning("Redis read failed for dedup check, assuming unseen")
            return False

    def add(self, url: str) -> None:
        try:
            self._client.set(self._key(url), "1", ex=self._ttl)
        except redis.RedisError:
            logger.warning("Redis write failed for dedup, key not persisted")


class InMemorySeenUrls:
    """Dedup backed by a bounded OrderedDict (fallback when Redis is unavailable)."""

    def __init__(self, max_size: int = MAX_SEEN_KEYS) -> None:
        self._keys: OrderedDict[str, None] = OrderedDict()
        self._max_size = max_size

    def contains(self, url: str) -> bool:
        return url in self._keys

    def add(self, url: str) -> None:
        self._keys[url] = None
        while len(self._keys) > self._max_size:
            self._keys.popitem(last=False)
