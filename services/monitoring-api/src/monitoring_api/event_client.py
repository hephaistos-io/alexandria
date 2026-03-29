"""PostgreSQL queries for detected events."""

import dataclasses
import json
import logging

import psycopg

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class EventArticle:
    """Article linked to a detected event."""

    id: int
    title: str
    source: str
    url: str
    summary: str | None
    published_at: str | None
    automatic_labels: list[str] | None
    entities: list[dict] | None


@dataclasses.dataclass
class EventConflict:
    """Conflict event linked to a detected event."""

    id: int
    title: str
    latitude: float
    longitude: float
    event_date: str | None
    place_desc: str
    source: str


@dataclasses.dataclass
class DashboardEvent:
    """Detected event data for the dashboard map."""

    id: int
    slug: str
    title: str
    status: str
    heat: float
    entity_qids: list[str]
    centroid_lat: float | None
    centroid_lng: float | None
    first_seen: str
    last_seen: str
    article_count: int
    conflict_count: int


@dataclasses.dataclass
class EventDetail:
    """Full event detail with linked articles and conflicts."""

    id: int
    slug: str
    title: str
    status: str
    heat: float
    entity_qids: list[str]
    centroid_lat: float | None
    centroid_lng: float | None
    first_seen: str
    last_seen: str
    article_count: int
    conflict_count: int
    articles: list[EventArticle]
    conflicts: list[EventConflict]


class EventClient:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def get_dashboard_events(self, since: str) -> list[DashboardEvent]:
        """Fetch active detected events that were still alive within the time window.

        Uses `last_seen` rather than `first_seen` because events are long-lived:
        an event first detected 7 days ago should still appear if it was active
        (updated) within the requested window.

        `since` must be an ISO 8601 string, e.g. "2024-01-15T00:00:00Z".
        A safety cap of 2000 rows prevents runaway memory usage.
        """
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT e.id, e.slug, e.title, e.status, e.heat,
                           e.entity_qids, e.centroid_lat, e.centroid_lng,
                           e.first_seen, e.last_seen,
                           COUNT(DISTINCT ea.article_id) AS article_count,
                           COUNT(DISTINCT ec.conflict_event_id) AS conflict_count
                    FROM events e
                    LEFT JOIN event_articles ea ON ea.event_id = e.id
                    LEFT JOIN event_conflicts ec ON ec.event_id = e.id
                    WHERE e.status != 'historical'
                      AND e.last_seen >= %s
                    GROUP BY e.id
                    ORDER BY e.heat DESC
                    LIMIT 2000
                    """,
                    (since,),
                )
                rows = cur.fetchall()

        return [
            DashboardEvent(
                id=int(row[0]),
                slug=str(row[1]),
                title=str(row[2]),
                status=str(row[3]),
                heat=round(float(row[4]), 4),
                entity_qids=row[5] or [],
                centroid_lat=float(row[6]) if row[6] is not None else None,
                centroid_lng=float(row[7]) if row[7] is not None else None,
                first_seen=row[8].isoformat() if row[8] else "",
                last_seen=row[9].isoformat() if row[9] else "",
                article_count=int(row[10]),
                conflict_count=int(row[11]),
            )
            for row in rows
        ]

    def get_event_detail(self, event_id: int) -> EventDetail | None:
        """Fetch full event detail including linked articles and conflicts."""
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                # 1. Fetch the event itself (with counts).
                cur.execute(
                    """
                    SELECT e.id, e.slug, e.title, e.status, e.heat,
                           e.entity_qids, e.centroid_lat, e.centroid_lng,
                           e.first_seen, e.last_seen,
                           COUNT(DISTINCT ea.article_id) AS article_count,
                           COUNT(DISTINCT ec.conflict_event_id) AS conflict_count
                    FROM events e
                    LEFT JOIN event_articles ea ON ea.event_id = e.id
                    LEFT JOIN event_conflicts ec ON ec.event_id = e.id
                    WHERE e.id = %s
                    GROUP BY e.id
                    """,
                    (event_id,),
                )
                event_row = cur.fetchone()
                if event_row is None:
                    return None

                # 2. Fetch linked articles.
                cur.execute(
                    """
                    SELECT a.id, a.title, a.source, a.url, a.summary,
                           a.published_at, a.automatic_labels, a.entities
                    FROM articles a
                    JOIN event_articles ea ON ea.article_id = a.id
                    WHERE ea.event_id = %s
                    ORDER BY a.published_at DESC NULLS LAST
                    LIMIT 500
                    """,
                    (event_id,),
                )
                article_rows = cur.fetchall()

                # 3. Fetch linked conflicts.
                cur.execute(
                    """
                    SELECT ce.id, ce.title, ce.latitude, ce.longitude,
                           ce.event_date, ce.place_desc, ce.source
                    FROM conflict_events ce
                    JOIN event_conflicts ec ON ec.conflict_event_id = ce.id
                    WHERE ec.event_id = %s
                    ORDER BY ce.event_date DESC NULLS LAST
                    LIMIT 500
                    """,
                    (event_id,),
                )
                conflict_rows = cur.fetchall()

        articles = []
        for r in article_rows:
            entities_raw = r[7]
            if isinstance(entities_raw, str):
                entities_raw = json.loads(entities_raw)
            articles.append(
                EventArticle(
                    id=int(r[0]),
                    title=str(r[1]),
                    source=str(r[2]),
                    url=str(r[3]),
                    summary=r[4],
                    published_at=r[5].isoformat() if r[5] else None,
                    automatic_labels=r[6],
                    entities=entities_raw,
                )
            )

        conflicts = [
            EventConflict(
                id=int(r[0]),
                title=str(r[1]),
                latitude=float(r[2]),
                longitude=float(r[3]),
                event_date=r[4].isoformat() if r[4] else None,
                place_desc=str(r[5]),
                source=str(r[6]),
            )
            for r in conflict_rows
        ]

        return EventDetail(
            id=int(event_row[0]),
            slug=str(event_row[1]),
            title=str(event_row[2]),
            status=str(event_row[3]),
            heat=round(float(event_row[4]), 4),
            entity_qids=event_row[5] or [],
            centroid_lat=float(event_row[6]) if event_row[6] is not None else None,
            centroid_lng=float(event_row[7]) if event_row[7] is not None else None,
            first_seen=event_row[8].isoformat() if event_row[8] else "",
            last_seen=event_row[9].isoformat() if event_row[9] else "",
            article_count=int(event_row[10]),
            conflict_count=int(event_row[11]),
            articles=articles,
            conflicts=conflicts,
        )
