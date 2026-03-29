"""PostgreSQL queries for the event detector.

All database access is in this module — the detector logic only works with
dataclasses, keeping SQL isolated and testable.
"""

import json
import logging

import psycopg

from event_detector.models import ArticleRow, ConflictRow, DetectedEvent, ExistingEvent

logger = logging.getLogger(__name__)


def fetch_recent_articles(conn: psycopg.Connection, days: int = 14) -> list[ArticleRow]:
    """Fetch articles from the last N days that have resolved entities.

    We only care about articles that have been through the entity-resolver
    (entities IS NOT NULL) because we cluster on Wikidata QIDs.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, title, entities, automatic_labels, published_at
            FROM articles
            WHERE entities IS NOT NULL
              AND COALESCE(published_at, created_at) > now() - make_interval(days => %s)
            ORDER BY COALESCE(published_at, created_at) DESC
            """,
            (days,),
        )
        rows = cur.fetchall()

    results: list[ArticleRow] = []
    for id_, title, entities_raw, auto_labels, published_at in rows:
        # entities is stored as JSONB — psycopg returns it as a Python object
        # already (list of dicts), but if it comes back as a string we parse it.
        if isinstance(entities_raw, str):
            entities_raw = json.loads(entities_raw)
        results.append(
            ArticleRow(
                id=int(id_),
                title=str(title),
                entities=entities_raw or [],
                automatic_labels=auto_labels,
                published_at=published_at,
            )
        )
    return results


def fetch_recent_conflicts(conn: psycopg.Connection, days: int = 14) -> list[ConflictRow]:
    """Fetch conflict events from the last N days."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, latitude, longitude, event_date, country
            FROM conflict_events
            WHERE COALESCE(event_date, created_at) > now() - make_interval(days => %s)
            """,
            (days,),
        )
        rows = cur.fetchall()

    return [
        ConflictRow(
            id=int(row[0]),
            latitude=float(row[1]),
            longitude=float(row[2]),
            event_date=row[3],
            country=row[4],
        )
        for row in rows
    ]


def fetch_existing_events(conn: psycopg.Connection) -> list[ExistingEvent]:
    """Fetch all non-historical events for matching against new clusters."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, slug, title, status, heat, entity_qids,
                   centroid_lat, centroid_lng, first_seen, last_seen
            FROM events
            WHERE status != 'historical'
            """,
        )
        rows = cur.fetchall()

    return [
        ExistingEvent(
            id=int(row[0]),
            slug=str(row[1]),
            title=str(row[2]),
            status=str(row[3]),
            heat=float(row[4]),
            entity_qids=row[5] or [],
            centroid_lat=float(row[6]) if row[6] is not None else None,
            centroid_lng=float(row[7]) if row[7] is not None else None,
            first_seen=row[8],
            last_seen=row[9],
        )
        for row in rows
    ]


def upsert_event(conn: psycopg.Connection, event: DetectedEvent) -> int:
    """Insert a new event or update an existing one.  Returns the event id."""
    with conn.cursor() as cur:
        if event.existing_id is not None:
            cur.execute(
                """
                UPDATE events
                SET title = %s, status = %s, heat = %s, entity_qids = %s,
                    centroid_lat = %s, centroid_lng = %s, last_seen = %s
                WHERE id = %s
                RETURNING id
                """,
                (
                    event.title,
                    event.status,
                    event.heat,
                    event.entity_qids,
                    event.centroid_lat,
                    event.centroid_lng,
                    event.last_seen,
                    event.existing_id,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO events (slug, title, status, heat, entity_qids,
                                    centroid_lat, centroid_lng, first_seen, last_seen)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (slug) DO UPDATE SET
                    title = EXCLUDED.title, status = EXCLUDED.status,
                    heat = EXCLUDED.heat, entity_qids = EXCLUDED.entity_qids,
                    centroid_lat = EXCLUDED.centroid_lat, centroid_lng = EXCLUDED.centroid_lng,
                    last_seen = EXCLUDED.last_seen
                RETURNING id
                """,
                (
                    event.slug,
                    event.title,
                    event.status,
                    event.heat,
                    event.entity_qids,
                    event.centroid_lat,
                    event.centroid_lng,
                    event.first_seen,
                    event.last_seen,
                ),
            )
        row = cur.fetchone()
        event_id = int(row[0])

    # Caller is responsible for conn.commit() — this allows wrapping
    # upsert + link_articles + link_conflicts in a single transaction.
    return event_id


def link_articles(conn: psycopg.Connection, event_id: int, article_ids: list[int]) -> None:
    """Replace the event's article links with the given set.

    Caller is responsible for conn.commit().
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM event_articles WHERE event_id = %s", (event_id,))
        if article_ids:
            cur.executemany(
                "INSERT INTO event_articles (event_id, article_id) VALUES (%s, %s) "
                "ON CONFLICT DO NOTHING",
                [(event_id, aid) for aid in article_ids],
            )


def link_conflicts(
    conn: psycopg.Connection,
    event_id: int,
    conflict_ids: list[int],
) -> None:
    """Replace the event's conflict event links with the given set.

    Caller is responsible for conn.commit().
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM event_conflicts WHERE event_id = %s", (event_id,))
        if conflict_ids:
            cur.executemany(
                "INSERT INTO event_conflicts (event_id, conflict_event_id) VALUES (%s, %s) "
                "ON CONFLICT DO NOTHING",
                [(event_id, cid) for cid in conflict_ids],
            )


def decay_historical_events(
    conn: psycopg.Connection,
    heat_threshold: float = 0.5,
    exclude_ids: set[int] | None = None,
) -> int:
    """Mark stale events as historical, excluding recently matched ones.

    Args:
        heat_threshold: Events below this heat score are candidates for decay.
        exclude_ids:    Event IDs matched this cycle — these are never decayed
                        even if their heat is below the threshold.

    Returns the number of events updated.
    """
    excluded = tuple(exclude_ids) if exclude_ids else ()
    with conn.cursor() as cur:
        if excluded:
            cur.execute(
                """
                UPDATE events SET status = 'historical'
                WHERE status != 'historical' AND heat < %s AND id != ALL(%s)
                RETURNING id
                """,
                (heat_threshold, list(excluded)),
            )
        else:
            cur.execute(
                """
                UPDATE events SET status = 'historical'
                WHERE status != 'historical' AND heat < %s
                RETURNING id
                """,
                (heat_threshold,),
            )
        count = cur.rowcount
    conn.commit()
    return count
