"""Entry point for the NASA EONET fetcher service.

Usage:
    uv run python -m nasa_eonet_fetcher

Configuration via environment variables:
    RABBITMQ_URL    - AMQP connection string. When unset, events are logged to stdout.
    REDIS_URL       - Redis for dedup + scheduling. When unset, in-memory fallback.
    FETCH_INTERVAL  - Seconds between fetch cycles (default: 1800 = 30 min).
"""

import logging
import os
import sys

import redis

from nasa_eonet_fetcher.dedup import InMemorySeenUrls, RedisSeenUrls, SeenUrls
from nasa_eonet_fetcher.fetcher import NasaEonetFetcher
from nasa_eonet_fetcher.logging import JsonFormatter
from nasa_eonet_fetcher.models import NaturalDisaster
from nasa_eonet_fetcher.publish import RabbitMqPublisher
from nasa_eonet_fetcher.runner import SmartFetchLoop


def _log_event(event: NaturalDisaster) -> None:
    logger.info("[NEW] %s — %s (%s)", event.title, event.category, event.source)


def main() -> None:
    rabbitmq_url = os.environ.get("RABBITMQ_URL")

    _raw_interval = os.environ.get("FETCH_INTERVAL", "1800")
    try:
        interval = int(_raw_interval)
    except ValueError:
        logger.error(
            "FETCH_INTERVAL must be an integer (got %r), using default 1800", _raw_interval
        )
        interval = 1800

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

    fetcher = NasaEonetFetcher()
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
logging.root.handlers[0].setFormatter(JsonFormatter("nasa-eonet-fetcher"))
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    main()
