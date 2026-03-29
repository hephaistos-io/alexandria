"""PostgreSQL queries for conflict event data."""

import dataclasses
import logging

import psycopg

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class DashboardConflictEvent:
    """Conflict event data for the dashboard map."""

    id: int
    source_id: str
    source: str
    title: str
    description: str | None
    latitude: float
    longitude: float
    event_date: str | None
    place_desc: str
    links: list[str]
    created_at: str


class ConflictClient:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def get_dashboard_events(self, since: str) -> list[DashboardConflictEvent]:
        """Fetch conflict events occurring/created since the given timestamp.

        `since` must be an ISO 8601 string, e.g. "2024-01-15T00:00:00Z".
        A safety cap of 2000 rows prevents runaway memory usage.
        """
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, source_id, source, title, description,
                           latitude, longitude, event_date, place_desc,
                           links, created_at
                    FROM conflict_events
                    WHERE COALESCE(event_date, created_at) >= %s
                    ORDER BY COALESCE(event_date, created_at) DESC
                    LIMIT 2000
                    """,
                    (since,),
                )
                rows = cur.fetchall()

        results: list[DashboardConflictEvent] = []
        for row in rows:
            (
                id_,
                source_id,
                source,
                title,
                description,
                latitude,
                longitude,
                event_date,
                place_desc,
                links,
                created_at,
            ) = row
            results.append(
                DashboardConflictEvent(
                    id=int(id_),
                    source_id=str(source_id),
                    source=str(source),
                    title=str(title),
                    description=description,
                    latitude=float(latitude),
                    longitude=float(longitude),
                    event_date=event_date.isoformat() if event_date else None,
                    place_desc=place_desc or "",
                    links=links or [],
                    created_at=created_at.isoformat() if created_at else "",
                )
            )
        return results
