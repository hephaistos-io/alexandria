"""URL deduplication backends for the fetch loop.

Two implementations:

- RedisSeenUrls: persists seen URLs as individual Redis keys with a TTL.
  Survives service restarts and is shared across all fetcher instances for
  the same origin.  Falls back gracefully on Redis errors — a missed dedup
  is better than a crashed service.

- InMemorySeenUrls: bounded OrderedDict, used when REDIS_URL is not set
  (local development without Docker).
"""

import logging
from collections import OrderedDict
from typing import Protocol

import redis

logger = logging.getLogger(__name__)

# Per-URL TTL: 7 days. If an article hasn't reappeared in a feed within
# a week, it's safe to forget about it and let dedup happen downstream
# (article-store rejects duplicate URLs at the DB level anyway).
_DEDUP_TTL_SECONDS = 7 * 24 * 60 * 60

# Upper bound for the in-memory fallback. ~50 articles per 15-minute
# cycle means 50,000 entries covers roughly 10 days of history.
MAX_SEEN_URLS = 50_000


class SeenUrls(Protocol):
    """Interface for URL deduplication backends."""

    def contains(self, url: str) -> bool:
        """Return True if this URL has been seen before."""
        ...

    def add(self, url: str) -> None:
        """Mark a URL as seen."""
        ...


class RedisSeenUrls:
    """Dedup backed by individual Redis keys, one per URL per origin.

    Each URL is stored as a key like ``seen:bbc_world:<url>`` with a 7-day
    TTL.  This means each URL expires independently — unlike a single SET
    where EXPIRE applies to the entire collection, individual keys age out
    on their own even while the fetcher keeps running.

    Redis errors are caught and logged — the service continues with a
    risk of occasional duplicates rather than crashing.
    """

    def __init__(self, redis_url: str, origin: str) -> None:
        self._client = redis.from_url(redis_url)
        self._prefix = f"seen:{origin}:"
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

    def _key(self, url: str) -> str:
        return self._prefix + url

    def contains(self, url: str) -> bool:
        try:
            return bool(self._client.exists(self._key(url)))
        except redis.RedisError:
            logger.warning("Redis read failed for dedup check, assuming unseen")
            return False

    def add(self, url: str) -> None:
        try:
            # SET with EX gives each URL its own independent TTL.
            # The value is irrelevant — we only check existence.
            self._client.set(self._key(url), "1", ex=self._ttl)
        except redis.RedisError:
            logger.warning("Redis write failed for dedup, URL not persisted")


class InMemorySeenUrls:
    """Dedup backed by a bounded OrderedDict (fallback when Redis is unavailable).

    Evicts the oldest entries when the cap is reached. Resets on restart.
    """

    def __init__(self, max_size: int = MAX_SEEN_URLS) -> None:
        self._urls: OrderedDict[str, None] = OrderedDict()
        self._max_size = max_size

    def contains(self, url: str) -> bool:
        return url in self._urls

    def add(self, url: str) -> None:
        self._urls[url] = None
        while len(self._urls) > self._max_size:
            self._urls.popitem(last=False)
