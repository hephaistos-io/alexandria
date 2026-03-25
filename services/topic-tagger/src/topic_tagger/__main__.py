"""Entry point for running topic-tagger as a module.

Usage:
    uv run python -m topic_tagger

Configuration via environment variables:
    RABBITMQ_URL    - AMQP connection string (required).
    DATABASE_URL    - PostgreSQL connection string (required).
    THRESHOLD       - Minimum classification score to emit a label (default: 0.3).
    MAX_LABELS      - Maximum number of labels to return per article (default: 3).
    LABEL_REFRESH   - Seconds between label reloads from DB (default: 300).
"""

import logging
import os
import sys
import threading
from datetime import datetime, timezone

from topic_tagger.classifier import TopicClassifier
from topic_tagger.consumer import MessageConsumer
from topic_tagger.labels import load_labels
from topic_tagger.logging import JsonFormatter
from topic_tagger.publish import RabbitMqPublisher

logger = logging.getLogger(__name__)

# Fields that every incoming message must contain.  These match what
# role-classifier publishes to articles.role-classified.
_REQUIRED_FIELDS = (
    "url",
    "title",
    "content",
    "entities",
)


def _setup_logging() -> None:
    """Configure structured JSON logging on the root logger."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter("topic-tagger"))
    logging.root.handlers.clear()
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)


def _schedule_label_refresh(
    classifier: TopicClassifier,
    database_url: str,
    interval_seconds: int,
) -> None:
    """Reload topic labels from the DB every `interval_seconds` seconds.

    Uses threading.Timer which is a lightweight way to schedule a callback
    without pulling in a full async runtime. Each callback reschedules itself,
    creating a recurring refresh loop.

    threading.Timer runs the callback in a background daemon thread — if the
    main process exits, the daemon thread is killed automatically.
    """
    def refresh() -> None:
        try:
            labels = load_labels(database_url)
            if labels:
                classifier.update_labels(labels)
        except Exception:
            logger.exception("Label refresh failed")
        # Reschedule regardless of success — we'll retry on the next interval.
        _schedule_label_refresh(classifier, database_url, interval_seconds)

    timer = threading.Timer(interval_seconds, refresh)
    timer.daemon = True
    timer.start()


def handle_message(
    payload: dict,
    classifier: TopicClassifier,
    publisher: RabbitMqPublisher,
) -> None:
    """Process one article from the articles.role-classified queue.

    Entities arrive pre-enriched with auto_role/auto_role_confidence
    from the upstream role-classifier service. This handler only does
    topic classification — it passes entities through unchanged.
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
    entities = payload.get("entities")

    if not isinstance(entities, list):
        logger.error("'entities' is not a list: %s", url)
        return

    # Prefer title + summary; fall back to content alone
    summary = payload.get("summary") or ""
    text = f"{title}. {summary}".strip() if (title or summary) else content

    if not text:
        logger.warning("Empty text for %s, skipping classification", url)
        return

    hits = classifier.classify(text)
    classified_at = datetime.now(timezone.utc).isoformat()

    # Publish when we have topic labels OR entity role annotations.
    # Entities arrive pre-enriched from the upstream role-classifier.
    # Articles with neither stay unlabelled — they can be picked up by
    # the manual labelling workflow or re-classified when labels change.
    has_entity_roles = any(e.get("auto_role") for e in entities)
    if hits or has_entity_roles:
        publisher.publish(
            url=url, labels=hits, classified_at=classified_at,
            entities=entities or None, title=title, content=content,
        )
        logger.info(
            "Classified %s → %s",
            url,
            [h["name"] for h in hits],
        )
    else:
        logger.debug("No labels above threshold for %s", url)


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

    threshold = float(os.environ.get("THRESHOLD", "0.3"))
    max_labels = int(os.environ.get("MAX_LABELS", "3"))
    label_refresh = int(os.environ.get("LABEL_REFRESH", "300"))

    # Load labels from the DB before starting the model.
    # If the DB is unavailable at startup we log a warning but continue —
    # the label refresh loop will pick them up once the DB comes online.
    labels = load_labels(database_url)
    if not labels:
        logger.warning(
            "No labels loaded at startup — classification will be skipped"
            " until labels are available"
        )

    # Load the model once. This takes 5–15s on first run (downloading weights)
    # or ~2s on subsequent runs (weights are cached in the Docker image layer).
    classifier = TopicClassifier(
        labels=labels, threshold=threshold, max_labels=max_labels
    )

    publisher = RabbitMqPublisher(rabbitmq_url)

    # Schedule periodic label refresh so the service picks up changes in the
    # classification_labels table without needing a restart.
    _schedule_label_refresh(classifier, database_url, label_refresh)

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
