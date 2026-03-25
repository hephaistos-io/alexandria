"""Entry point for running article-store as a module.

Usage:
    uv run python -m article_store

Configuration via environment variables:
    RABBITMQ_URL    - AMQP connection string (required).
    DATABASE_URL    - PostgreSQL connection string (required).
"""

import logging
import os
import sys

from article_store.consumer import MessageConsumer
from article_store.logging import JsonFormatter
from article_store.store import ArticleStore

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure structured JSON logging on the root logger.

    Clears existing handlers first to avoid duplicate log lines if this
    module is loaded more than once (e.g. in tests).
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter("article-store"))
    logging.root.handlers.clear()
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)


def main() -> None:
    _setup_logging()

    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    database_url = os.environ.get("DATABASE_URL")
    if not rabbitmq_url:
        logger.error("RABBITMQ_URL is required")
        sys.exit(1)
    if not database_url:
        logger.error("DATABASE_URL is required")
        sys.exit(1)

    store = ArticleStore(database_url)

    def handle_message(payload: dict) -> None:
        saved = store.save(payload)
        if saved:
            logger.info("Stored article: %s", payload.get("url", "???"))
        else:
            logger.debug("Duplicate skipped: %s", payload.get("url", "???"))

    consumer = MessageConsumer(rabbitmq_url, on_message=handle_message)
    try:
        consumer.start()
    finally:
        consumer.close()
        store.close()


if __name__ == "__main__":
    main()
