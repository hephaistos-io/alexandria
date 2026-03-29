"""Conflict consumer — reads raw conflict events from RabbitMQ and writes them to PostgreSQL.

Entry point:
    uv run python -m article_store.conflict_consumer

Configuration via environment variables:
    RABBITMQ_URL   - AMQP connection string (required).
    DATABASE_URL   - PostgreSQL connection string (required).

This module is intentionally kept separate from the main article-store entry
point (__main__.py). It runs as its own process in Docker with a different
CMD, consuming from the conflict_events.raw queue instead of articles.training.
That way the two consumers can scale independently.

Message format (published by conflict data-ingestion services):
    {
        "source_id":   "12345",
        "source":      "ACLED",
        "title":       "Airstrike in northern region",
        "description": "An airstrike was reported...",   (optional)
        "latitude":    34.5,
        "longitude":   69.2,
        "event_date":  "2026-03-15T00:00:00Z",           (optional)
        "place_desc":  "Kabul, Afghanistan",              (optional)
        "links":       ["https://example.com/event/1"],  (optional)
        "fetched_at":  "2026-03-27T10:00:00Z"
    }
"""

import logging
import os
import sys

import psycopg

from article_store.consumer import MessageConsumer
from article_store.logging import JsonFormatter
from article_store.schema import apply_schema

CONSUME_QUEUE = "conflict_events.raw"

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure structured JSON logging on the root logger."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter("conflict-store"))
    logging.root.handlers.clear()
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)


class ConflictWriter:
    """Writes conflict events to PostgreSQL using a long-lived connection.

    A single connection is reused for the lifetime of the process, matching
    the pattern in ArticleStore and LabelWriter.  This avoids the overhead of
    opening a new TCP + TLS connection on every message.

    apply_schema() is called in __init__ so that this process can start
    independently and still create the conflict_events table if it does not
    yet exist.
    """

    def __init__(self, database_url: str) -> None:
        logger.info("Connecting to PostgreSQL")
        self._conn = psycopg.connect(database_url)
        apply_schema(self._conn)

    def save(self, payload: dict) -> bool:
        """Insert one conflict event row.

        Returns True if the row was inserted, False if it was a duplicate
        (source + source_id already present — ON CONFLICT DO NOTHING).
        """
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO conflict_events "
                "    (source_id, source, title, description, latitude, longitude, "
                "     event_date, country, place_desc, links, fetched_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (source, source_id) DO NOTHING",
                (
                    payload["source_id"],
                    payload["source"],
                    payload["title"],
                    payload.get("description"),
                    payload["latitude"],
                    payload["longitude"],
                    payload.get("event_date"),
                    payload.get("country"),
                    payload.get("place_desc"),
                    payload.get("links"),
                    payload["fetched_at"],
                ),
            )
            inserted = cur.rowcount > 0
        self._conn.commit()
        return inserted

    def close(self) -> None:
        """Close the PostgreSQL connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            logger.info("PostgreSQL connection closed")


def handle_message(payload: dict, writer: ConflictWriter) -> None:
    """Process one raw conflict event message.

    Validates required fields before proceeding.  Missing required fields
    are logged as errors and the message is dropped (not re-queued).
    """
    required_fields = ("source_id", "source", "title", "latitude", "longitude", "fetched_at")
    for field in required_fields:
        if field not in payload or payload[field] is None:
            logger.error("Message missing or empty required field '%s'", field)
            return

    # Defense-in-depth: reject (0, 0) coordinates even though upstream fetchers
    # already filter these. A direct producer could still send them.
    if payload["latitude"] == 0.0 and payload["longitude"] == 0.0:
        logger.warning("Rejecting event with (0, 0) coordinates: %s", payload.get("source_id"))
        return

    inserted = writer.save(payload)
    if inserted:
        logger.info(
            "Conflict event stored: source=%s source_id=%s",
            payload["source"],
            payload["source_id"],
        )
    else:
        logger.info(
            "Duplicate conflict event skipped: source=%s source_id=%s",
            payload["source"],
            payload["source_id"],
        )


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

    writer = ConflictWriter(database_url)

    consumer = MessageConsumer(
        rabbitmq_url,
        on_message=lambda payload: handle_message(payload, writer),
        queue=CONSUME_QUEUE,
    )
    logger.info("Conflict consumer started, consuming from '%s'", CONSUME_QUEUE)
    try:
        consumer.start()
    finally:
        consumer.close()
        writer.close()


if __name__ == "__main__":
    main()
