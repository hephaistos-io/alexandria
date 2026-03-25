"""Label updater — consumes classification results and writes them to PostgreSQL.

Entry point:
    uv run python -m article_store.label_updater

Configuration via environment variables:
    RABBITMQ_URL   - AMQP connection string (required).
    DATABASE_URL   - PostgreSQL connection string (required).

This module is intentionally kept separate from the main article-store entry
point (__main__.py). It runs as its own process in Docker with a different
CMD, consuming from the articles.classified.store queue instead of
articles.training. That way the two consumers can scale independently.

Message format (published by topic-tagger):
    {
        "url": "https://example.com/article",
        "labels": [{"name": "CONFLICT", "score": 0.85}, {"name": "POLITICS", "score": 0.42}],
        "classified_at": "2026-03-21T10:00:00Z"
    }
"""

import json
import logging
import os
import sys

import psycopg

from article_store.consumer import MessageConsumer
from article_store.logging import JsonFormatter

CONSUME_QUEUE = "articles.classified.store"

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure structured JSON logging on the root logger."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter("label-updater"))
    logging.root.handlers.clear()
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)


class LabelWriter:
    """Writes automatic labels to PostgreSQL using a long-lived connection.

    A single connection is reused for the lifetime of the process, matching
    the pattern in ArticleStore.  This avoids the overhead of opening a new
    TCP + TLS connection on every message — significant when processing a
    steady stream of classification results.
    """

    def __init__(self, database_url: str) -> None:
        logger.info("Connecting to PostgreSQL")
        self._conn = psycopg.connect(database_url)

    def update_automatic_labels(
        self,
        url: str,
        labels: list[str],
        classified_at: str,
        entities: list[dict] | None = None,
    ) -> bool:
        """Write automatic_labels, classified_at, and entities for the given URL.

        Returns True if a row was updated, False if the URL wasn't found.
        """
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE articles "
                "SET automatic_labels = %s, classified_at = %s, "
                "    entities = %s::jsonb "
                "WHERE url = %s",
                (
                    labels,
                    classified_at,
                    json.dumps(entities) if entities else None,
                    url,
                ),
            )
            updated = cur.rowcount > 0
        self._conn.commit()
        return updated

    def close(self) -> None:
        """Close the PostgreSQL connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            logger.info("PostgreSQL connection closed")


def handle_message(payload: dict, writer: LabelWriter) -> None:
    """Process one classification result message.

    Validates required fields before proceeding.  Each label dict must
    have a "name" key — malformed entries are logged and skipped.
    """
    url = payload.get("url")
    if not url:
        logger.error("Message missing or empty 'url' field")
        return

    # The topic-tagger publishes labels as [{"name": "CONFLICT", "score": 0.85}, ...].
    # We extract just the name strings for the automatic_labels TEXT[] column.
    raw_labels = payload.get("labels", [])
    labels: list[str] = []
    for label_dict in raw_labels:
        if not isinstance(label_dict, dict) or "name" not in label_dict:
            logger.warning(
                "Skipping malformed label entry %r for %s", label_dict, url,
            )
            continue
        labels.append(label_dict["name"])

    classified_at: str = payload.get("classified_at", "")
    entities = payload.get("entities")

    updated = writer.update_automatic_labels(url, labels, classified_at, entities)
    if updated:
        logger.info("Auto-labels written for %s: %s", url, labels)
    else:
        logger.warning("URL not found in articles table: %s", url)


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

    writer = LabelWriter(database_url)

    consumer = MessageConsumer(
        rabbitmq_url,
        on_message=lambda payload: handle_message(payload, writer),
        queue=CONSUME_QUEUE,
    )
    logger.info("Label updater started, consuming from '%s'", CONSUME_QUEUE)
    try:
        consumer.start()
    finally:
        consumer.close()
        writer.close()


if __name__ == "__main__":
    main()
