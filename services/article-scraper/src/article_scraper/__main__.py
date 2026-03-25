"""Entry point for running the article scraper as a module.

Usage:
    uv run python -m article_scraper

Configuration via environment variables:
    RABBITMQ_URL       - AMQP connection string (required).
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

from article_scraper.consumer import MessageConsumer
from article_scraper.models import RssArticle
from article_scraper.publish import RabbitMqPublisher
from article_scraper.scraper import scrape_article


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects for structured logging."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        message = record.getMessage()
        # logger.exception() sets exc_info — include the traceback so we
        # can actually diagnose failures instead of swallowing them.
        if record.exc_info and record.exc_info[1] is not None:
            message += "\n" + self.formatException(record.exc_info)
        entry = {
            "ts": ts,
            "level": record.levelname.lower(),
            "service": self._service,
            "logger": record.name,
            "message": message,
        }
        return json.dumps(entry)


logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure structured JSON logging on the root logger.

    Clears existing handlers first to avoid duplicate log lines if this
    module is somehow loaded more than once (e.g. in tests).
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter("article-scraper"))
    logging.root.handlers.clear()
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)


_REQUIRED_FIELDS = ("source", "origin", "title", "url", "summary", "fetched_at")


def handle_message(payload: dict, publisher: RabbitMqPublisher) -> None:
    """Process one message from the articles.rss queue.

    Validates that all required fields are present before constructing
    an RssArticle.  A missing field logs an explicit error instead of
    an opaque KeyError traceback.
    """
    missing = [f for f in _REQUIRED_FIELDS if f not in payload]
    if missing:
        logger.error(
            "Message missing required fields %s: %s",
            missing, payload.get("url", "<no url>"),
        )
        return

    article = RssArticle(
        source=payload["source"],
        origin=payload["origin"],
        title=payload["title"],
        url=payload["url"],
        summary=payload["summary"],
        published=payload.get("published"),
        fetched_at=payload["fetched_at"],
    )

    result = scrape_article(article)
    if result is None:
        logger.warning("Skipping (extraction failed): %s", article.url)
        return

    publisher.publish(result)
    logger.info("Published scraped article: %s", article.url)


def main() -> None:
    _setup_logging()

    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        logger.error("RABBITMQ_URL is required")
        sys.exit(1)

    publisher = RabbitMqPublisher(rabbitmq_url)

    consumer = MessageConsumer(
        rabbitmq_url,
        on_message=lambda payload: handle_message(payload, publisher),
    )
    consumer.start()


if __name__ == "__main__":
    main()
