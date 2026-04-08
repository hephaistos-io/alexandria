"""PostgreSQL queries for natural disaster data (NASA EONET)."""

import dataclasses
import logging

import psycopg

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class DashboardDisaster:
    """Natural disaster data for the dashboard map."""

    id: int
    source_id: str
    source: str
    title: str
    description: str | None
    category: str
    latitude: float
    longitude: float
    geometry_type: str
    event_date: str | None
    closed_at: str | None
    magnitude_value: float | None
    magnitude_unit: str | None
    links: list[str]
    # Full EONET geometry timeline (each entry is `{date, type, coordinates,
    # magnitudeValue?, magnitudeUnit?}`). Stored as JSONB on the row, returned
    # to the frontend as a plain list of dicts. The frontend uses this for
    # animated tracks; the scalar lat/lng/magnitude columns above remain
    # the source of truth for "render this on the map right now".
    geometries: list[dict]
    created_at: str


class DisasterClient:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def get_dashboard_events(self, since: str) -> list[DashboardDisaster]:
        """Fetch natural disasters occurring/created since the given timestamp.

        `since` must be an ISO 8601 string, e.g. "2024-01-15T00:00:00Z".
        A safety cap of 2000 rows prevents runaway memory usage.
        """
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, source_id, source, title, description, category,
                           latitude, longitude, geometry_type, event_date, closed_at,
                           magnitude_value, magnitude_unit, links, geometries, created_at
                    FROM natural_disasters
                    WHERE COALESCE(event_date, created_at) >= %s
                    ORDER BY COALESCE(event_date, created_at) DESC
                    LIMIT 2000
                    """,
                    (since,),
                )
                rows = cur.fetchall()

        results: list[DashboardDisaster] = []
        for row in rows:
            (
                id_,
                source_id,
                source,
                title,
                description,
                category,
                latitude,
                longitude,
                geometry_type,
                event_date,
                closed_at,
                magnitude_value,
                magnitude_unit,
                links,
                geometries,
                created_at,
            ) = row
            results.append(
                DashboardDisaster(
                    id=int(id_),
                    source_id=str(source_id),
                    source=str(source),
                    title=str(title),
                    description=description,
                    category=str(category),
                    latitude=float(latitude),
                    longitude=float(longitude),
                    geometry_type=str(geometry_type),
                    event_date=event_date.isoformat() if event_date else None,
                    closed_at=closed_at.isoformat() if closed_at else None,
                    magnitude_value=float(magnitude_value) if magnitude_value is not None else None,
                    magnitude_unit=magnitude_unit,
                    links=links or [],
                    # psycopg3 decodes JSONB to native Python lists/dicts,
                    # so no json.loads needed here.
                    geometries=geometries or [],
                    created_at=created_at.isoformat() if created_at else "",
                )
            )
        return results
