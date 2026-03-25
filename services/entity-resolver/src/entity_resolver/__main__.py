"""Entry point for running the entity resolver as a module.

Usage:
    uv run python -m entity_resolver

Configuration via environment variables:
    RABBITMQ_URL       - AMQP connection string (required).
    REDIS_URL          - Redis connection string (required).
"""

import logging
import os
import sys
from datetime import datetime, timezone

from entity_resolver.consumer import DEFAULT_CONSUME_QUEUE, MessageConsumer
from entity_resolver.logging import JsonFormatter
from entity_resolver.models import ResolvedArticle
from entity_resolver.publish import RabbitMqPublisher
from entity_resolver.resolver import RateLimitedError, WikidataResolver

# How many times an article can be re-enqueued before we give up and publish
# it with partially-resolved entities.  Each retry only hits Wikidata for
# entities that failed previously — successful lookups are instant cache hits.
MAX_RESOLVE_RETRIES = 3

logger = logging.getLogger(__name__)

# Fields that must be present in every incoming message.  Without these
# the downstream ResolvedArticle cannot be constructed.
_REQUIRED_FIELDS = (
    "url", "source", "origin", "title", "summary",
    "content", "fetched_at", "scraped_at", "tagged_at",
)


def _setup_logging() -> None:
    """Configure structured JSON logging to stdout."""
    logging.root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter("entity-resolver"))
    logging.root.setLevel(logging.INFO)
    logging.root.addHandler(handler)


def handle_message(
    payload: dict,
    resolver: WikidataResolver,
    publisher: RabbitMqPublisher,
) -> None:
    """Process one message from the articles.tagged queue.

    If any entity lookup is rate-limited by Wikidata, the entire article
    is re-enqueued (up to MAX_RESOLVE_RETRIES times) instead of being
    published downstream with gaps.  Successfully resolved entities are
    cached in Redis, so retries only hit Wikidata for the failed ones.
    """
    url = payload.get("url")
    if not url:
        logger.error("Message missing or empty 'url' field")
        return

    missing = [f for f in _REQUIRED_FIELDS if f not in payload]
    if missing:
        logger.error("Message missing required fields %s: %s", missing, url)
        return

    entities = payload.get("entities", [])
    resolved_entities = []
    was_rate_limited = False

    for ent in entities:
        if not isinstance(ent, dict) or "text" not in ent:
            logger.warning("Skipping malformed entity entry %r for %s", ent, url)
            resolved_entities.append({
                **(ent if isinstance(ent, dict) else {}),
                "wikidata_id": None,
                "canonical_name": None,
                "description": None,
                "latitude": None,
                "longitude": None,
            })
            continue

        try:
            result = resolver.resolve(ent["text"], label=ent.get("label"))
        except RateLimitedError:
            result = None
            was_rate_limited = True
        resolved_entities.append({
            **ent,
            "wikidata_id": result["wikidata_id"] if result else None,
            "canonical_name": result["label"] if result else None,
            "description": result["description"] if result else None,
            "latitude": result.get("latitude") if result else None,
            "longitude": result.get("longitude") if result else None,
        })

    retries = payload.get("_resolve_retries", 0)

    if was_rate_limited and retries < MAX_RESOLVE_RETRIES:
        # Re-enqueue to the back of the input queue for another attempt.
        # The _resolve_retries counter travels with the payload so we
        # know when to give up. All other fields are untouched.
        payload["_resolve_retries"] = retries + 1
        publisher.requeue(payload, DEFAULT_CONSUME_QUEUE)
        logger.info(
            "Re-enqueued %s for retry (%d/%d) due to rate limiting",
            url,
            retries + 1,
            MAX_RESOLVE_RETRIES,
        )
        return

    if was_rate_limited:
        logger.warning(
            "Max retries (%d) reached for %s, publishing partially resolved",
            MAX_RESOLVE_RETRIES,
            url,
        )

    resolved_count = sum(1 for e in resolved_entities if e["wikidata_id"] is not None)

    article = ResolvedArticle(
        source=payload["source"],
        origin=payload["origin"],
        title=payload["title"],
        url=url,
        summary=payload["summary"],
        published=payload.get("published"),
        fetched_at=payload["fetched_at"],
        content=payload["content"],
        scraped_at=payload["scraped_at"],
        entities=resolved_entities,
        tagged_at=payload["tagged_at"],
        resolved_at=datetime.now(timezone.utc).isoformat(),
    )
    publisher.publish(article)
    logger.info(
        "Resolved %s (%d/%d entities linked)",
        url,
        resolved_count,
        len(entities),
    )


def main() -> None:
    _setup_logging()

    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        logger.error("RABBITMQ_URL is required")
        sys.exit(1)

    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        logger.error("REDIS_URL is required")
        sys.exit(1)

    # Create the resolver once at startup — it holds a connection pool to Redis
    # and a persistent httpx.Client. Both are reused for every message.
    #
    # Authentication priority:
    #   1. WIKIDATA_API_TOKEN  — personal API token (simplest, never expires)
    #   2. WIKIDATA_CLIENT_ID + WIKIDATA_CLIENT_SECRET — OAuth2 (4h JWT)
    #   3. Neither — unauthenticated (~500 req/hr)
    api_token = os.environ.get("WIKIDATA_API_TOKEN")
    client_id = os.environ.get("WIKIDATA_CLIENT_ID")
    client_secret = os.environ.get("WIKIDATA_CLIENT_SECRET")
    resolver = WikidataResolver(
        redis_url,
        api_token=api_token,
        client_id=client_id,
        client_secret=client_secret,
    )
    logger.info("WikidataResolver initialised")

    publisher = RabbitMqPublisher(rabbitmq_url)
    consumer = MessageConsumer(
        rabbitmq_url,
        on_message=lambda payload: handle_message(payload, resolver, publisher),
    )

    try:
        consumer.start()
    finally:
        consumer.close()
        publisher.close()
        resolver.close()


if __name__ == "__main__":
    main()
