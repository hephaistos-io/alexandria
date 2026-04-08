"""Disaster consumer — reads natural disaster events from RabbitMQ and writes them to PostgreSQL.

Entry point:
    uv run python -m article_store.disaster_consumer

Configuration via environment variables:
    RABBITMQ_URL   - AMQP connection string (required).
    DATABASE_URL   - PostgreSQL connection string (required).

This mirrors `conflict_consumer.py` but listens on a different queue and
writes to a different table. The two consumers run as separate processes so
they can scale and be restarted independently.

Message format (published by nasa-eonet-fetcher):
    {
        "source_id":       "EONET_1234",
        "source":          "nasa_eonet",
        "title":           "Wildfire — Northern California",
        "description":     "Active wildfire in the foothills",       (optional)
        "category":        "wildfires",
        "latitude":        38.7,
        "longitude":       -120.5,
        "geometry_type":   "Point",
        "event_date":      "2026-04-01T00:00:00+00:00",              (optional)
        "closed_at":       "2026-04-05T18:00:00+00:00",              (optional)
        "magnitude_value": 12500.0,                                   (optional)
        "magnitude_unit":  "acres",                                   (optional)
        "links":           ["https://inciweb.example/123"],           (optional)
        "fetched_at":      "2026-04-08T12:00:00+00:00"
    }
"""

import logging
import os
import sys

import psycopg
from psycopg.types.json import Jsonb

from article_store.consumer import MessageConsumer
from article_store.logging import JsonFormatter
from article_store.schema import apply_schema

CONSUME_QUEUE = "natural_disasters.raw"

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure structured JSON logging on the root logger."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter("disaster-store"))
    logging.root.handlers.clear()
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)


class DisasterWriter:
    """Writes natural disaster events to PostgreSQL using a long-lived connection.

    A single connection is reused for the lifetime of the process, matching
    the pattern in ConflictWriter and ArticleStore.  This avoids the overhead
    of opening a new TCP + TLS connection on every message.

    apply_schema() is called in __init__ so that this process can start
    independently and still create the natural_disasters table if it does
    not yet exist.
    """

    def __init__(self, database_url: str) -> None:
        logger.info("Connecting to PostgreSQL")
        self._conn = psycopg.connect(database_url)
        apply_schema(self._conn)

    def save(self, payload: dict) -> bool:
        """Insert one natural disaster row.

        Returns True if the row was inserted, False if it was a duplicate
        (source + source_id already present — ON CONFLICT DO NOTHING).
        """
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO natural_disasters "
                "    (source_id, source, title, description, category, "
                "     latitude, longitude, geometry_type, event_date, closed_at, "
                "     magnitude_value, magnitude_unit, links, geometries, fetched_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (source, source_id) DO NOTHING",
                (
                    payload["source_id"],
                    payload["source"],
                    payload["title"],
                    payload.get("description"),
                    payload["category"],
                    payload["latitude"],
                    payload["longitude"],
                    payload["geometry_type"],
                    payload.get("event_date"),
                    payload.get("closed_at"),
                    payload.get("magnitude_value"),
                    payload.get("magnitude_unit"),
                    payload.get("links"),
                    # Wrap in psycopg's Jsonb adapter so the list is sent
                    # as JSONB rather than a stringified array. Falls back
                    # to an empty list if the producer omits the field
                    # (defensive — the fetcher always sets it).
                    Jsonb(payload.get("geometries") or []),
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


def handle_message(payload: dict, writer: DisasterWriter) -> None:
    """Process one raw natural disaster event message.

    Validates required fields before proceeding.  Missing required fields
    are logged as errors and the message is dropped (not re-queued).
    """
    required_fields = (
        "source_id",
        "source",
        "title",
        "category",
        "latitude",
        "longitude",
        "geometry_type",
        "fetched_at",
    )
    for field in required_fields:
        if field not in payload or payload[field] is None:
            logger.error("Message missing or empty required field '%s'", field)
            return

    # Defense-in-depth: reject (0, 0) coordinates. The fetcher already filters
    # null/missing geometry, but a direct producer could still send these.
    if payload["latitude"] == 0.0 and payload["longitude"] == 0.0:
        logger.warning("Rejecting disaster with (0, 0) coordinates: %s", payload.get("source_id"))
        return

    inserted = writer.save(payload)
    if inserted:
        logger.info(
            "Disaster stored: source=%s source_id=%s category=%s",
            payload["source"],
            payload["source_id"],
            payload["category"],
        )
    else:
        logger.info(
            "Duplicate disaster skipped: source=%s source_id=%s",
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

    writer = DisasterWriter(database_url)

    consumer = MessageConsumer(
        rabbitmq_url,
        on_message=lambda payload: handle_message(payload, writer),
        queue=CONSUME_QUEUE,
    )
    logger.info("Disaster consumer started, consuming from '%s'", CONSUME_QUEUE)
    try:
        consumer.start()
    finally:
        consumer.close()
        writer.close()


if __name__ == "__main__":
    main()
