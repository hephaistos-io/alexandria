"""Entry point for the GDELT fetcher service.

Usage:
    uv run python -m gdelt_fetcher

Configuration via environment variables:
    RABBITMQ_URL       - AMQP connection string. When unset, events are logged to stdout.
    REDIS_URL          - Redis for dedup + scheduling. When unset, in-memory fallback.
    FETCH_INTERVAL     - Seconds between fetch cycles (default: 900 = 15 minutes).
"""

import logging
import os
import sys

import redis

from gdelt_fetcher.dedup import InMemorySeenUrls, RedisSeenUrls, SeenUrls
from gdelt_fetcher.fetcher import GdeltFetcher
from gdelt_fetcher.logging import JsonFormatter
from gdelt_fetcher.models import ConflictEvent
from gdelt_fetcher.publish import RabbitMqPublisher
from gdelt_fetcher.runner import SmartFetchLoop


def _log_event(event: ConflictEvent) -> None:
    logger.info("[NEW] %s — %s (%s)", event.title, event.place_desc, event.source)


def main() -> None:
    rabbitmq_url = os.environ.get("RABBITMQ_URL")

    _raw_interval = os.environ.get("FETCH_INTERVAL", "900")
    try:
        interval = int(_raw_interval)
    except ValueError:
        logger.error(
            "FETCH_INTERVAL must be an integer (got %r), using default 900", _raw_interval
        )
        interval = 900

    sleep_fn = None
    if rabbitmq_url:
        publisher = RabbitMqPublisher(rabbitmq_url)
        on_event = publisher.publish
        sleep_fn = publisher.sleep
    else:
        on_event = _log_event

    redis_url = os.environ.get("REDIS_URL")
    seen: SeenUrls
    redis_client = None
    if redis_url:
        redis_client = redis.from_url(redis_url)
        seen = RedisSeenUrls(redis_url)
    else:
        logger.info("REDIS_URL not set — using in-memory dedup (resets on restart)")
        seen = InMemorySeenUrls()

    fetcher = GdeltFetcher()
    loop = SmartFetchLoop(
        fetcher,
        on_event=on_event,
        interval_seconds=interval,
        sleep_fn=sleep_fn,
        seen=seen,
        redis_client=redis_client,
    )
    loop.run()


logging.basicConfig(handlers=[logging.StreamHandler(sys.stdout)], level=logging.INFO, force=True)
logging.root.handlers[0].setFormatter(JsonFormatter("gdelt-fetcher"))
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    main()
