"""Entry point for the event detector service.

Usage:
    uv run python -m event_detector

Configuration via environment variables:
    DATABASE_URL        - PostgreSQL connection string (required).
    REDIS_URL           - Redis for resume-aware scheduling. When unset, runs immediately.
    DETECTION_INTERVAL  - Seconds between detection cycles (default: 300 = 5 minutes).
    LOOKBACK_DAYS       - How many days of articles/conflicts to consider (default: 14).
"""

import logging
import os
import sys
import time

import psycopg
import redis as redis_lib

from event_detector.detector import (
    build_event,
    cluster_articles,
    compute_entity_idf,
    match_existing_event,
)
from event_detector.logging import JsonFormatter
from event_detector.queries import (
    decay_historical_events,
    fetch_existing_events,
    fetch_recent_articles,
    fetch_recent_conflicts,
    link_articles,
    link_conflicts,
    upsert_event,
)

LAST_DETECTION_KEY = "event_detector:last_detection_ts"


def run_cycle(database_url: str, lookback_days: int) -> None:
    """Run one detection cycle: fetch → cluster → score → write."""
    with psycopg.connect(database_url) as conn:
        articles = fetch_recent_articles(conn, days=lookback_days)
        conflicts = fetch_recent_conflicts(conn, days=lookback_days)
        existing_events = fetch_existing_events(conn)

    logger.info(
        "Fetched %d articles, %d conflicts, %d existing events",
        len(articles),
        len(conflicts),
        len(existing_events),
    )

    if not articles:
        logger.info("No articles to cluster — skipping")
        return

    idf = compute_entity_idf(articles)
    clusters = cluster_articles(articles, idf)
    logger.info("Found %d cluster(s) from %d articles", len(clusters), len(articles))

    # Track which existing events were matched so we can decay the rest.
    matched_event_ids: set[int] = set()

    for cluster in clusters:
        # Determine the cluster's entity signature for matching.
        cluster_qids: set[str] = set()
        for article in cluster:
            for ent in article.entities:
                qid = ent.get("wikidata_id")
                if qid:
                    cluster_qids.add(qid)

        existing = match_existing_event(cluster_qids, existing_events)
        if existing:
            matched_event_ids.add(existing.id)

        event = build_event(cluster, conflicts, idf, existing)

        # Single connection + transaction for all three writes so they
        # either all succeed or all roll back (no partial state).
        with psycopg.connect(database_url) as conn:
            event_id = upsert_event(conn, event)
            link_articles(conn, event_id, event.article_ids)
            link_conflicts(conn, event_id, event.conflict_ids)
            conn.commit()

        action = "Updated" if existing else "Created"
        logger.info(
            "%s event '%s' (id=%d, heat=%.2f, status=%s, articles=%d, conflicts=%d)",
            action,
            event.title,
            event_id,
            event.heat,
            event.status,
            len(event.article_ids),
            len(event.conflict_ids),
        )

    # Decay events that weren't matched by any cluster this cycle.
    with psycopg.connect(database_url) as conn:
        decayed = decay_historical_events(conn, exclude_ids=matched_event_ids)

    if decayed:
        logger.info("Marked %d event(s) as historical", decayed)


def _get_last_ts(redis_client: redis_lib.Redis | None) -> float | None:
    if redis_client is None:
        return None
    try:
        val = redis_client.get(LAST_DETECTION_KEY)
        return float(val) if val else None
    except redis_lib.RedisError:
        logger.warning("Failed to read last detection timestamp from Redis")
        return None


def _set_last_ts(redis_client: redis_lib.Redis | None) -> None:
    if redis_client is None:
        return
    try:
        redis_client.set(LAST_DETECTION_KEY, str(time.time()))
    except redis_lib.RedisError:
        logger.warning("Failed to write last detection timestamp to Redis")


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL is required")
        sys.exit(1)

    raw_interval = os.environ.get("DETECTION_INTERVAL", "300")
    try:
        interval = int(raw_interval)
    except ValueError:
        logger.error(
            "DETECTION_INTERVAL must be an integer (got %r), using default 300",
            raw_interval,
        )
        interval = 300

    raw_lookback = os.environ.get("LOOKBACK_DAYS", "14")
    try:
        lookback_days = int(raw_lookback)
    except ValueError:
        logger.error("LOOKBACK_DAYS must be an integer (got %r), using default 14", raw_lookback)
        lookback_days = 14

    redis_url = os.environ.get("REDIS_URL")
    redis_client: redis_lib.Redis | None = None
    if redis_url:
        redis_client = redis_lib.from_url(redis_url)
    else:
        logger.info("REDIS_URL not set — no resume-aware scheduling")

    # Smart startup: sleep until next cycle is due (same pattern as fetchers).
    last_ts = _get_last_ts(redis_client)
    if last_ts is not None:
        wait = (last_ts + interval) - time.time()
        if wait > 0:
            logger.info(
                "Last detection %.0fs ago, next in %.0fs — sleeping",
                time.time() - last_ts,
                wait,
            )
            time.sleep(wait)
        else:
            logger.info("Last detection %.0fs ago (overdue) — running now", time.time() - last_ts)
    else:
        logger.info("No previous detection recorded — running immediately")

    while True:
        try:
            run_cycle(database_url, lookback_days)
            _set_last_ts(redis_client)
        except Exception:
            logger.exception("Detection cycle failed, will retry next cycle")
        time.sleep(interval)


# Module-level logging setup (runs on import, before main).
logging.basicConfig(handlers=[logging.StreamHandler(sys.stdout)], level=logging.INFO, force=True)
logging.root.handlers[0].setFormatter(JsonFormatter("event-detector"))
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    main()
