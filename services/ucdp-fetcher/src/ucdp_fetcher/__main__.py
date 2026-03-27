"""Entry point for the UCDP fetcher service.

Usage:
    uv run python -m ucdp_fetcher

Configuration via environment variables:
    RABBITMQ_URL        - AMQP connection string. When unset, events are logged to stdout.
    REDIS_URL           - Redis for dedup + scheduling. When unset, in-memory fallback.
    FETCH_INTERVAL      - Seconds between fetch cycles (default: 604800 = 1 week).
    UCDP_ACCESS_TOKEN   - API access token for the UCDP GED Candidate API.
                          When unset, the service exits cleanly (token is required).
"""

import logging
import os
import sys

import redis

from ucdp_fetcher.dedup import InMemorySeenUrls, RedisSeenUrls, SeenUrls
from ucdp_fetcher.fetcher import UcdpFetcher
from ucdp_fetcher.logging import JsonFormatter
from ucdp_fetcher.models import ConflictEvent
from ucdp_fetcher.publish import RabbitMqPublisher
from ucdp_fetcher.runner import SmartFetchLoop


def _log_event(event: ConflictEvent) -> None:
    logger.info("[NEW] %s — %s (%s)", event.title, event.place_desc, event.source)


def main() -> None:
    access_token = os.environ.get("UCDP_ACCESS_TOKEN")
    if not access_token:
        logger.info(
            "UCDP_ACCESS_TOKEN not set — sleeping indefinitely. "
            "Set this environment variable and restart the container to enable the UCDP fetcher."
        )
        # Stay alive so the container shows as running in the infrastructure view.
        # Using an infinite sleep instead of sys.exit() avoids restart loops and
        # keeps the container visible in monitoring dashboards.
        import time

        while True:
            time.sleep(3600)

    rabbitmq_url = os.environ.get("RABBITMQ_URL")

    _raw_interval = os.environ.get("FETCH_INTERVAL", "604800")
    try:
        interval = int(_raw_interval)
    except ValueError:
        logger.error(
            "FETCH_INTERVAL must be an integer (got %r), using default 604800", _raw_interval
        )
        interval = 604800

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

    fetcher = UcdpFetcher(access_token)
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
logging.root.handlers[0].setFormatter(JsonFormatter("ucdp-fetcher"))
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    main()
