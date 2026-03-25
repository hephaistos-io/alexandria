"""Entry point for running role-classifier as a module.

Usage:
    uv run python -m role_classifier

Configuration via environment variables:
    RABBITMQ_URL    - AMQP connection string (required).
    DATABASE_URL    - PostgreSQL connection string (required).
    LABEL_REFRESH   - Seconds between role type reloads from DB (default: 300).
"""

import logging
import os
import sys
import threading
from datetime import datetime, timezone

from role_classifier.classifier import RoleClassifier
from role_classifier.consumer import MessageConsumer
from role_classifier.labels import load_role_types
from role_classifier.logging import JsonFormatter
from role_classifier.publish import RabbitMqPublisher

logger = logging.getLogger(__name__)

# Fields that every incoming message must contain.  These match what
# entity-resolver publishes to articles.resolved.
_REQUIRED_FIELDS = (
    "url",
    "title",
    "content",
    "entities",
)


def _setup_logging() -> None:
    """Configure structured JSON logging on the root logger."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter("role-classifier"))
    logging.root.handlers.clear()
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)


def _schedule_role_type_refresh(
    classifier: RoleClassifier,
    database_url: str,
    interval_seconds: int,
) -> None:
    """Reload role types from the DB every `interval_seconds` seconds.

    Uses threading.Timer which is a lightweight way to schedule a callback
    without pulling in a full async runtime. Each callback reschedules itself,
    creating a recurring refresh loop.

    threading.Timer runs the callback in a background daemon thread — if the
    main process exits, the daemon thread is killed automatically.
    """
    def refresh() -> None:
        try:
            role_types = load_role_types(database_url)
            if role_types:
                classifier.update_role_types(role_types)
        except Exception:
            logger.exception("Role type refresh failed")
        # Reschedule regardless of success — we'll retry on the next interval.
        _schedule_role_type_refresh(classifier, database_url, interval_seconds)

    timer = threading.Timer(interval_seconds, refresh)
    timer.daemon = True
    timer.start()


def handle_message(
    payload: dict,
    classifier: RoleClassifier,
    publisher: RabbitMqPublisher,
) -> None:
    """Process one article from the articles.resolved queue.

    Classifies geographic entity roles using the full content for context,
    stamps a role_classified_at timestamp, then publishes the full payload
    unconditionally. Downstream consumers need every message — even articles
    with no geo entities or no role assignments — to keep their own state
    consistent.
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

    # Classify roles and annotate entities in place.
    # classify_entity_roles() is a no-op if role_types or entities is empty.
    classified_entities = classifier.classify_entity_roles(
        entities, title, content
    )

    # Stamp a classification timestamp regardless of whether any roles
    # were assigned — downstream can use this to know the message has
    # been through the role-classifier stage.
    payload["entities"] = classified_entities
    payload["role_classified_at"] = datetime.now(timezone.utc).isoformat()

    publisher.publish(payload)

    roles_assigned = sum(
        1 for e in classified_entities if e.get("auto_role")
    )
    logger.info(
        "Role-classified %s — %d/%d entities annotated",
        url,
        roles_assigned,
        len(classified_entities),
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

    label_refresh = int(os.environ.get("LABEL_REFRESH", "300"))

    # Load role types from the DB before starting the model.
    # If the DB is unavailable at startup we log a warning but continue —
    # the refresh loop will pick them up once the DB comes online.
    role_types = load_role_types(database_url)
    if not role_types:
        logger.warning(
            "No role types loaded at startup — entity role classification"
            " will be skipped until role types are available"
        )

    # Load the model once. This takes 5–15s on first run (downloading weights)
    # or ~2s on subsequent runs (weights are cached in the Docker image layer).
    classifier = RoleClassifier(role_types=role_types)

    publisher = RabbitMqPublisher(rabbitmq_url)

    # Schedule periodic role type refresh so the service picks up changes in
    # the entity_role_types table without needing a restart.
    _schedule_role_type_refresh(classifier, database_url, label_refresh)

    def _on_message(payload: dict) -> None:
        handle_message(payload, classifier, publisher)

    consumer = MessageConsumer(rabbitmq_url, on_message=_on_message)
    try:
        consumer.start()
    finally:
        consumer.close()
        publisher.close()


if __name__ == "__main__":
    main()
