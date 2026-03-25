"""Entry point for running the NER tagger as a module.

Usage:
    uv run python -m ner_tagger

Configuration via environment variables:
    RABBITMQ_URL       - AMQP connection string (required).
"""

import logging
import os
import sys
from datetime import datetime, timezone

from ner_tagger.consumer import MessageConsumer
from ner_tagger.logging import JsonFormatter
from ner_tagger.models import TaggedArticle
from ner_tagger.publish import RabbitMqPublisher
from ner_tagger.tagger import NerTagger

logger = logging.getLogger(__name__)

# Fields that every incoming message must contain.  These match what
# article-fetcher publishes to articles.raw.
_REQUIRED_FIELDS = (
    "url",
    "source",
    "origin",
    "title",
    "summary",
    "fetched_at",
    "scraped_at",
)


def _setup_logging() -> None:
    """Configure structured JSON logging on the root logger."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter("ner-tagger"))
    # force=True via handlers.clear() — avoids duplicate output if a handler
    # was already registered (e.g. by a library or test harness).
    logging.root.handlers.clear()
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)


def handle_message(
    payload: dict,
    tagger: NerTagger,
    publisher: RabbitMqPublisher,
) -> None:
    """Process one message from the articles.raw queue.

    Validates required fields, runs NER tagging, and publishes the
    enriched article to articles.tagged.
    """
    url = payload.get("url")
    if not url:
        logger.error("Message missing or empty 'url' field")
        return

    missing = [f for f in _REQUIRED_FIELDS if f not in payload]
    if missing:
        logger.error("Message missing required fields %s: %s", missing, url)
        return

    content = payload.get("content", "")
    mentions = tagger.tag(content)

    tagged = TaggedArticle(
        source=payload["source"],
        origin=payload["origin"],
        title=payload["title"],
        url=url,
        summary=payload["summary"],
        published=payload.get("published"),
        fetched_at=payload["fetched_at"],
        content=content,
        scraped_at=payload["scraped_at"],
        entities=[
            {
                "text": m.text,
                "label": m.label,
                "start": m.start_char,
                "end": m.end_char,
            }
            for m in mentions
        ],
        tagged_at=datetime.now(timezone.utc).isoformat(),
    )

    publisher.publish(tagged)
    logger.info("Tagged %s (%d entities)", url, len(tagged.entities))


def main() -> None:
    _setup_logging()

    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        logger.error("RABBITMQ_URL is required")
        sys.exit(1)

    # Load the spaCy model once at startup (~100MB in memory for en_core_web_sm).
    # Reused for every message — no per-message model loading overhead.
    tagger = NerTagger()
    logger.info("spaCy model loaded")

    publisher = RabbitMqPublisher(rabbitmq_url)

    def _on_message(payload: dict) -> None:
        handle_message(payload, tagger, publisher)

    consumer = MessageConsumer(rabbitmq_url, on_message=_on_message)

    try:
        consumer.start()
    finally:
        consumer.close()
        publisher.close()


if __name__ == "__main__":
    main()
