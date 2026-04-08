"""Key deduplication backends for the fetch loop.

Two implementations:

- RedisSeenUrls: persists seen keys as individual Redis keys with a TTL.
  Survives service restarts and is shared across all fetcher instances.
  Falls back gracefully on Redis errors — a missed dedup is better than
  a crashed service.

- InMemorySeenUrls: bounded OrderedDict, used when REDIS_URL is not set
  (local development without Docker).
"""

import logging
from collections import OrderedDict
from typing import Protocol

import redis

logger = logging.getLogger(__name__)

# Per-key TTL: 30 days. EONET events can stay open for weeks (long-lived
# wildfires, ongoing volcanic activity), so we want a TTL comfortably longer
# than the typical event lifetime to avoid re-publishing the same event.
_DEDUP_TTL_SECONDS = 30 * 24 * 60 * 60

# Upper bound for the in-memory fallback. EONET typically returns a few
# hundred open events at any time; 50k is plenty of headroom.
MAX_SEEN_KEYS = 50_000


class SeenUrls(Protocol):
    """Interface for deduplication backends.

    Despite the name (kept for consistency with article-fetcher), this protocol
    works with any string key — not just URLs.
    """

    def contains(self, url: str) -> bool:
        """Return True if this key has been seen before."""
        ...

    def add(self, url: str) -> None:
        """Mark a key as seen."""
        ...


class RedisSeenUrls:
    """Dedup backed by individual Redis keys, one per event.

    Each event is stored as a key like ``seen:disaster:<source>:<source_id>``
    with a 30-day TTL.  Individual keys age out independently — unlike a single
    Redis SET where EXPIRE applies to the entire collection.

    Redis errors are caught and logged — the service continues with a risk of
    occasional duplicates rather than crashing.
    """

    def __init__(self, redis_url: str) -> None:
        self._client = redis.from_url(redis_url)
        self._prefix = "seen:disaster:"
        self._ttl = _DEDUP_TTL_SECONDS

        # Validate connectivity at startup so mis-configurations are
        # caught early with a clear error message.
        try:
            self._client.ping()
            logger.info(
                "Redis dedup enabled (prefix=%s, ttl=%ds)", self._prefix, self._ttl,
            )
        except redis.RedisError:
            logger.error(
                "Redis ping failed at startup — dedup writes will be attempted "
                "but may fail. Check REDIS_URL.",
            )

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
            # SET with EX gives each key its own independent TTL.
            # The value is irrelevant — we only check existence.
            self._client.set(self._key(url), "1", ex=self._ttl)
        except redis.RedisError:
            logger.warning("Redis write failed for dedup, key not persisted")


class InMemorySeenUrls:
    """Dedup backed by a bounded OrderedDict (fallback when Redis is unavailable).

    Evicts the oldest entries when the cap is reached. Resets on restart.
    """

    def __init__(self, max_size: int = MAX_SEEN_KEYS) -> None:
        self._keys: OrderedDict[str, None] = OrderedDict()
        self._max_size = max_size

    def contains(self, url: str) -> bool:
        return url in self._keys

    def add(self, url: str) -> None:
        self._keys[url] = None
        while len(self._keys) > self._max_size:
            self._keys.popitem(last=False)
