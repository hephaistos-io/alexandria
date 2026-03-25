"""Entry point for running relation-extractor as a module.

Usage:
    uv run python -m relation_extractor

Configuration via environment variables:
    RABBITMQ_URL        - AMQP connection string (required).
    DATABASE_URL        - PostgreSQL connection string (required).
    NEO4J_URL           - Neo4j bolt URI (required).
    NEO4J_AUTH          - Neo4j credentials as "user/password" (required).
    RELATION_THRESHOLD  - Minimum NLI confidence to emit a relation (default: 0.65).
    LABEL_REFRESH       - Seconds between DB relation type reloads (default: 300).
"""

import logging
import os
import sys
import threading

from relation_extractor.consumer import MessageConsumer
from relation_extractor.extractor import RelationExtractor
from relation_extractor.labels import load_relation_types
from relation_extractor.logging import JsonFormatter
from relation_extractor.neo4j_writer import Neo4jWriter

logger = logging.getLogger(__name__)

# Fields that every incoming message must contain.  These match what
# topic-tagger publishes to articles.classified.relation.
_REQUIRED_FIELDS = (
    "url",
    "title",
    "content",
    "entities",
)


def _setup_logging() -> None:
    """Configure structured JSON logging on the root logger."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter("relation-extractor"))
    logging.root.handlers.clear()
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)


def _parse_neo4j_auth(auth_str: str) -> tuple[str, str]:
    """Parse a "user/password" string into a (user, password) tuple.

    Raises ValueError if the string doesn't contain exactly one slash.
    We split on the first slash only to allow passwords that contain slashes.
    """
    parts = auth_str.split("/", 1)
    if len(parts) != 2:
        raise ValueError(
            f"NEO4J_AUTH must be in 'user/password' format, got: {auth_str!r}"
        )
    return parts[0], parts[1]


def _schedule_relation_type_refresh(
    extractor: RelationExtractor,
    database_url: str,
    interval_seconds: int,
) -> None:
    """Reload relation types from the DB every `interval_seconds` seconds.

    Uses threading.Timer which is a lightweight way to schedule a callback
    without pulling in a full async runtime. Each callback reschedules itself,
    creating a recurring refresh loop.

    threading.Timer runs the callback in a background daemon thread — if the
    main process exits, the daemon thread is killed automatically.
    """
    def refresh() -> None:
        relation_types = load_relation_types(database_url)
        if relation_types:
            extractor.update_relation_types(relation_types)
        # Reschedule regardless of success — we'll retry on the next interval.
        _schedule_relation_type_refresh(extractor, database_url, interval_seconds)

    timer = threading.Timer(interval_seconds, refresh)
    timer.daemon = True
    timer.start()


def handle_message(
    payload: dict,
    extractor: RelationExtractor,
    writer: Neo4jWriter,
) -> None:
    """Process one article from the articles.classified.relation queue.

    This is a terminal consumer — output goes to Neo4j rather than being
    forwarded to another queue.
    """
    url = payload.get("url")
    if not url:
        logger.error("Message missing or empty 'url' field")
        return

    missing = [f for f in _REQUIRED_FIELDS if f not in payload]
    if missing:
        logger.error("Message missing required fields %s: %s", missing, url)
        return

    title = payload.get("title", "")
    content = payload.get("content", "")
    entities = payload.get("entities") or []

    if not isinstance(entities, list):
        logger.error("'entities' is not a list: %s", url)
        return

    if not entities:
        logger.debug("Skipping article with no entities: %s", url)
        return

    if not content:
        logger.debug("Skipping article with no content: %s", url)
        return

    relations = extractor.extract_relations(entities, title, content)

    if relations:
        writer.upsert_relations(relations, url)

    resolved_count = sum(1 for e in entities if e.get("wikidata_id"))
    logger.info(
        "Extracted %d relations from %d resolved entities for %s",
        len(relations),
        resolved_count,
        url,
    )


def main() -> None:
    _setup_logging()

    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    database_url = os.environ.get("DATABASE_URL")
    neo4j_url = os.environ.get("NEO4J_URL")
    neo4j_auth_str = os.environ.get("NEO4J_AUTH")

    if not rabbitmq_url:
        logger.error("RABBITMQ_URL is required")
        sys.exit(1)
    if not database_url:
        logger.error("DATABASE_URL is required")
        sys.exit(1)
    if not neo4j_url:
        logger.error("NEO4J_URL is required")
        sys.exit(1)
    if not neo4j_auth_str:
        logger.error("NEO4J_AUTH is required")
        sys.exit(1)

    try:
        neo4j_auth = _parse_neo4j_auth(neo4j_auth_str)
    except ValueError as exc:
        logger.error("Invalid NEO4J_AUTH: %s", exc)
        sys.exit(1)

    threshold = float(os.environ.get("RELATION_THRESHOLD", "0.65"))
    label_refresh = int(os.environ.get("LABEL_REFRESH", "300"))

    # Load relation types from the DB before starting the model.
    # If the DB is unavailable at startup we log a warning but continue —
    # the refresh loop will pick them up once the DB comes online.
    relation_types = load_relation_types(database_url)
    if not relation_types:
        logger.warning(
            "No relation types loaded at startup — relation extraction"
            " will be skipped until relation types are available"
        )

    # Load the model once. This takes 5–15s on first run (downloading weights)
    # or ~2s on subsequent runs (weights are cached in the Docker image layer).
    extractor = RelationExtractor(
        relation_types=relation_types, threshold=threshold
    )

    writer = Neo4jWriter(uri=neo4j_url, auth=neo4j_auth)

    # Schedule periodic relation type refresh so the service picks up changes
    # in the relation_types table without needing a restart.
    _schedule_relation_type_refresh(extractor, database_url, label_refresh)

    def _on_message(payload: dict) -> None:
        handle_message(payload, extractor, writer)

    consumer = MessageConsumer(rabbitmq_url, on_message=_on_message)
    try:
        consumer.start()
    finally:
        consumer.close()
        writer.close()


if __name__ == "__main__":
    main()
