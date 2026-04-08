"""Fetches natural disaster events from the NASA EONET API.

EONET is the Earth Observatory Natural Event Tracker — a free, unauthenticated
public API that aggregates natural disaster events (wildfires, severe storms,
volcanoes, sea/lake ice, etc.) from a variety of NASA and partner sources.

API docs: https://eonet.gsfc.nasa.gov/docs/v3
"""

import logging
from datetime import datetime, timezone

import httpx

from nasa_eonet_fetcher.models import NaturalDisaster

logger = logging.getLogger(__name__)

API_BASE = "https://eonet.gsfc.nasa.gov/api/v3"

# `status=all` includes both currently-open and recently-closed events.
# Without it the API only returns open events, which would hide closed
# wildfires, ended storms, etc. that are still relevant for a "last 7 days"
# style view.
#
# `days=30` is a generous backfill window — EONET events can stay open for
# weeks, and we want enough history that the dashboard's longest time range
# (30D) has data even on a fresh deployment.
DEFAULT_DAYS = 30


class NasaEonetFetcher:
    """Fetches natural disaster events from the NASA EONET v3 API."""

    def __init__(self, days: int = DEFAULT_DAYS) -> None:
        self._days = days

    def fetch(self) -> list[NaturalDisaster]:
        """Fetch open + closed events from EONET for the configured backfill window."""
        url = f"{API_BASE}/events?status=all&days={self._days}"
        logger.info("Fetching EONET events (days=%d)", self._days)
        now = datetime.now(timezone.utc)

        try:
            response = httpx.get(url, timeout=60.0)
            response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("EONET API request failed")
            return []

        data = response.json()
        raw_events = data.get("events", [])
        logger.info("EONET returned %d raw events", len(raw_events))

        events: list[NaturalDisaster] = []
        for item in raw_events:
            event = self._normalize(item, now)
            if event is not None:
                events.append(event)

        logger.info("EONET normalized to %d events with valid geometry", len(events))
        return events

    def _normalize(self, item: dict, fetched_at: datetime) -> NaturalDisaster | None:
        """Convert one EONET event dict into a NaturalDisaster row.

        EONET events have an array of geometries (a wildfire spreading over
        days = many daily observations). For v1 we collapse to a single row
        per event using the most recent geometry as the marker location.
        """
        eonet_id = item.get("id")
        title = item.get("title")
        if not eonet_id or not title:
            return None

        geometries = item.get("geometry") or []
        latest = self._latest_geometry(geometries)
        if latest is None:
            # Event has no usable geometry — skip it. EONET sometimes returns
            # events with empty geometry arrays during ingest transitions.
            return None

        coords = self._extract_point(latest)
        if coords is None:
            return None
        latitude, longitude = coords
        geometry_type = latest.get("type", "Point")

        event_date = self._parse_iso(latest.get("date"))
        closed_at = self._parse_iso(item.get("closed"))

        # `categories` is an array of {id, title}. Comma-join the IDs so the
        # storage column can be a single TEXT — most events have just one
        # category, and joining keeps the schema simple.
        categories = item.get("categories") or []
        category = ",".join(c.get("id", "") for c in categories if c.get("id"))
        if not category:
            category = "unknown"

        # `sources` is an array of {id, url}. We just want the URLs.
        sources = item.get("sources") or []
        links = [s["url"] for s in sources if s.get("url")]

        # IMPORTANT: in EONET v3, magnitudeValue/magnitudeUnit live on the
        # geometry, NOT on the event. (For storms each observation has its
        # own wind speed; for wildfires each observation has its own area.)
        # We copy the latest observation's magnitude into the scalar column
        # so it can be filtered and used to drive marker sizing without a
        # JSONB lookup.
        magnitude_value = self._parse_float(latest.get("magnitudeValue"))
        magnitude_unit = latest.get("magnitudeUnit") if magnitude_value is not None else None

        return NaturalDisaster(
            source_id=str(eonet_id),
            source="nasa_eonet",
            title=str(title),
            description=item.get("description"),
            category=category,
            latitude=latitude,
            longitude=longitude,
            geometry_type=geometry_type,
            event_date=event_date,
            closed_at=closed_at,
            magnitude_value=magnitude_value,
            magnitude_unit=magnitude_unit,
            links=links,
            fetched_at=fetched_at,
            # Pass the full geometry array through verbatim — the consumer
            # stores it as JSONB so the frontend can render tracks/timelines
            # without a follow-up backend change.
            geometries=geometries,
        )

    def _latest_geometry(self, geometries: list[dict]) -> dict | None:
        """Pick the most recent geometry from an EONET event's geometry array.

        Geometries arrive ordered oldest-first in practice, but we sort
        defensively by parsed `date` so we don't depend on upstream ordering.
        Geometries with unparseable or missing dates fall to the bottom.
        """
        if not geometries:
            return None

        def sort_key(g: dict) -> datetime:
            parsed = self._parse_iso(g.get("date"))
            # `datetime.min` is naive; make it tz-aware so it sorts cleanly
            # against the parsed (tz-aware) values from EONET.
            return parsed if parsed is not None else datetime.min.replace(tzinfo=timezone.utc)

        return sorted(geometries, key=sort_key)[-1]

    def _extract_point(self, geometry: dict) -> tuple[float, float] | None:
        """Reduce an EONET geometry to a single (lat, lng) tuple.

        EONET geometries follow GeoJSON conventions:

        - Point:    coordinates = [lng, lat]
        - Polygon:  coordinates = [[[lng, lat], [lng, lat], ...]]
                    (an outer ring, optionally followed by inner holes)

        For Polygons we compute a simple coordinate centroid (mean of vertices)
        as the marker location. This isn't the geographic centroid of the
        enclosed area — it's good enough for dropping a single map marker on
        an irregular shape like a wildfire perimeter or sea ice extent.

        IMPORTANT: GeoJSON puts longitude before latitude in coordinate pairs.
        This is a common footgun — most APIs use [lat, lng]. EONET follows
        GeoJSON, so we have to flip the order on extraction.
        """
        gtype = geometry.get("type")
        coords = geometry.get("coordinates")
        if not coords:
            return None

        if gtype == "Point":
            try:
                lng, lat = float(coords[0]), float(coords[1])
            except (TypeError, ValueError, IndexError):
                return None
            return (lat, lng)

        if gtype == "Polygon":
            try:
                outer_ring = coords[0]  # first ring is the outer boundary
                if not outer_ring:
                    return None
                lat_sum = 0.0
                lng_sum = 0.0
                count = 0
                for pair in outer_ring:
                    lng_sum += float(pair[0])
                    lat_sum += float(pair[1])
                    count += 1
                if count == 0:
                    return None
                return (lat_sum / count, lng_sum / count)
            except (TypeError, ValueError, IndexError):
                return None

        # Unknown geometry type (LineString, MultiPolygon, etc.) — skip.
        return None

    def _parse_iso(self, value: object) -> datetime | None:
        """Parse an ISO 8601 timestamp, returning None on any failure.

        EONET sometimes returns dates with a trailing 'Z' for UTC, which
        Python's `fromisoformat` only accepts as of 3.11. We're on 3.13 so
        this is fine, but the explicit replace keeps it robust if EONET
        changes formats.
        """
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _parse_float(self, value: object) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def source_name(self) -> str:
        return "nasa_eonet"
