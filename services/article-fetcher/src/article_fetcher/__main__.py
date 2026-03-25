"""Entry point for running the article fetcher as a module.

Usage:
    uv run python -m article_fetcher

Configuration via environment variables:
    RABBITMQ_URL       - AMQP connection string (e.g. amqp://rabbitmq:5672).
                         When set, articles are published to RabbitMQ.
                         When unset, articles are logged to stdout.
    REDIS_URL          - Redis connection string (e.g. redis://redis:6379/0).
                         When set, URL dedup is persisted in Redis.
                         When unset, falls back to bounded in-memory dedup.
    FETCH_INTERVAL     - Seconds between fetch cycles (default: 900).
    FEED_URL           - RSS feed URL to poll (default: BBC World News).
    ORIGIN             - Origin label attached to each article (default: bbc_world).
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

from article_fetcher import FetchLoop, RssFetcher
from article_fetcher.dedup import InMemorySeenUrls, RedisSeenUrls, SeenUrls
from article_fetcher.models import Article
from article_fetcher.publish import RabbitMqPublisher
from article_fetcher.sources.aljazeera import clean_url as aljazeera_clean_url
from article_fetcher.sources.dw import clean_url as dw_clean_url


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects for structured logging.

    Each line looks like:
        {"ts": "2026-03-21T10:15:00Z", "level": "info", "service": "article-fetcher",
         "logger": "article_fetcher.runner", "message": "Fetched 10 articles"}

    Why subclass Formatter instead of using basicConfig's format string?
    Because we need to emit JSON — the built-in format strings only produce
    plain text. Overriding `format()` gives us full control over the output.
    """

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        # datetime.now(timezone.utc) gives us a timezone-aware UTC datetime.
        # strftime with %Y-%m-%dT%H:%M:%SZ produces the ISO 8601 format the
        # spec requires. We drop sub-second precision to keep logs readable.
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        entry = {
            "ts": ts,
            "level": record.levelname.lower(),
            "service": self._service,
            "logger": record.name,
            # record.getMessage() interpolates the format args (e.g. "foo %s" % bar).
            "message": record.getMessage(),
        }
        return json.dumps(entry)


# Some feeds append tracking parameters to URLs. Map origin → cleaner so the
# RssFetcher stores canonical URLs (important for deduplication downstream).
URL_CLEANERS = {
    "aljazeera": aljazeera_clean_url,
    "dw_world": dw_clean_url,
}


def _log_article(article: Article) -> None:
    logger.info("[NEW] %s — %s", article.title, article.url)


def main() -> None:
    rabbitmq_url = os.environ.get("RABBITMQ_URL")

    _raw_interval = os.environ.get("FETCH_INTERVAL", "900")
    try:
        interval = int(_raw_interval)
    except ValueError:
        logger.error("FETCH_INTERVAL must be an integer (got %r), using default 900", _raw_interval)
        interval = 900
    feed_url = os.environ.get("FEED_URL", "https://feeds.bbci.co.uk/news/world/rss.xml")
    origin = os.environ.get("ORIGIN", "bbc_world")

    # When RabbitMQ is configured, use the publisher's sleep method so that
    # heartbeat frames are processed between fetch cycles.  Without this,
    # time.sleep() blocks pika's I/O and RabbitMQ kills the connection
    # after its heartbeat timeout expires (default 120s).
    sleep_fn = None
    if rabbitmq_url:
        publisher = RabbitMqPublisher(rabbitmq_url)
        on_article = publisher.publish
        sleep_fn = publisher.sleep
    else:
        on_article = _log_article

    # URL deduplication: use Redis when available, fall back to in-memory.
    # Redis dedup survives restarts and is shared across instances of the
    # same origin.  In-memory dedup resets on restart but works without
    # any external dependencies.
    redis_url = os.environ.get("REDIS_URL")
    seen_urls: SeenUrls
    if redis_url:
        seen_urls = RedisSeenUrls(redis_url, origin=origin)
    else:
        logger.info("REDIS_URL not set — using in-memory dedup (resets on restart)")
        seen_urls = InMemorySeenUrls()

    fetcher = RssFetcher(feed_url=feed_url, origin=origin, url_cleaner=URL_CLEANERS.get(origin))
    loop = FetchLoop(
        fetcher,
        on_article=on_article,
        interval_seconds=interval,
        sleep_fn=sleep_fn,
        seen_urls=seen_urls,
    )
    loop.run()


# Logging must be configured at module level so it's ready before main().
# But the service logic is inside main() so that importing this module
# (e.g. in tests or IDE tooling) doesn't trigger side effects.
logging.basicConfig(handlers=[logging.StreamHandler(sys.stdout)], level=logging.INFO, force=True)
logging.root.handlers[0].setFormatter(JsonFormatter("article-fetcher"))
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    main()
