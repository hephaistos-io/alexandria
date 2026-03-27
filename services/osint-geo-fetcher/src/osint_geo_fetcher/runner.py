"""Fetch loop with startup-aware scheduling."""

import logging
import time
from collections.abc import Callable

import redis as redis_lib

from osint_geo_fetcher.dedup import InMemorySeenUrls, SeenUrls
from osint_geo_fetcher.fetcher import OsintGeoFetcher
from osint_geo_fetcher.models import ConflictEvent

logger = logging.getLogger(__name__)

LAST_FETCH_KEY = "osint_geo_fetcher:last_fetch_ts"


class SmartFetchLoop:
    def __init__(
        self,
        fetcher: OsintGeoFetcher,
        on_event: Callable[[ConflictEvent], None],
        interval_seconds: int = 10800,
        sleep_fn: Callable[[float], None] | None = None,
        seen: SeenUrls | None = None,
        redis_client: redis_lib.Redis | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._on_event = on_event
        self._interval = interval_seconds
        self._sleep = sleep_fn if sleep_fn is not None else time.sleep
        self._seen = seen if seen is not None else InMemorySeenUrls()
        self._redis = redis_client

    def _dedup_key(self, event: ConflictEvent) -> str:
        return f"{event.source}:{event.source_id}"

    def _get_last_fetch_ts(self) -> float | None:
        if self._redis is None:
            return None
        try:
            val = self._redis.get(LAST_FETCH_KEY)
            return float(val) if val else None
        except redis_lib.RedisError:
            logger.warning("Failed to read last fetch timestamp from Redis")
            return None

    def _set_last_fetch_ts(self) -> None:
        if self._redis is None:
            return
        try:
            self._redis.set(LAST_FETCH_KEY, str(time.time()))
        except redis_lib.RedisError:
            logger.warning("Failed to write last fetch timestamp to Redis")

    def fetch_new(self) -> list[ConflictEvent]:
        events = self._fetcher.fetch()
        new = [e for e in events if not self._seen.contains(self._dedup_key(e))]
        delivered: list[ConflictEvent] = []
        for event in new:
            try:
                self._on_event(event)
                self._seen.add(self._dedup_key(event))
                delivered.append(event)
            except Exception:
                logger.exception(
                    "Failed to deliver event %s:%s, will retry next cycle",
                    event.source,
                    event.source_id,
                )
        return delivered

    def run(self) -> None:
        logger.info(
            "Starting smart fetch loop (source=%s, interval=%ds)",
            self._fetcher.source_name(),
            self._interval,
        )

        # Smart startup: check if we need to wait before the first fetch.
        last_ts = self._get_last_fetch_ts()
        if last_ts is not None:
            next_due = last_ts + self._interval
            wait = next_due - time.time()
            if wait > 0:
                logger.info(
                    "Last fetch was %.0fs ago, next due in %.0fs — sleeping",
                    time.time() - last_ts,
                    wait,
                )
                self._sleep(wait)
            else:
                logger.info(
                    "Last fetch was %.0fs ago (overdue) — fetching now", time.time() - last_ts
                )
        else:
            logger.info("No previous fetch recorded — fetching immediately")

        while True:
            try:
                new_events = self.fetch_new()
                logger.info("Cycle done: %d new event(s)", len(new_events))
                self._set_last_fetch_ts()
            except Exception:
                logger.exception("Fetch cycle failed, will retry next cycle")
            self._sleep(self._interval)
