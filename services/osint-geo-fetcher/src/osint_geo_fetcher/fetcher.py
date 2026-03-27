"""Fetches conflict events from multiple OSINT sources via osint-geo-extractor."""

import hashlib
import logging
from collections.abc import Callable
from datetime import datetime, timezone

import geo_extractor

from osint_geo_fetcher.models import ConflictEvent

logger = logging.getLogger(__name__)

# Map of source name → extractor function.
# Each function returns List[Event] with fields: id, date, latitude, longitude,
# place_desc, title, description, source, links.
# The package installs as `geo_extractor` (PyPI name: osint-geo-extractor).
SOURCES: dict[str, Callable[[], list]] = {
    "bellingcat": geo_extractor.get_bellingcat_data,
    "ceninfores": geo_extractor.get_ceninfores_data,
    "defmon": geo_extractor.get_defmon_data,
    "geoconfirmed": geo_extractor.get_geoconfirmed_data,
    "texty": geo_extractor.get_texty_data,
}


class OsintGeoFetcher:
    """Fetches and normalizes conflict events from all osint-geo-extractor sources."""

    def fetch(self) -> list[ConflictEvent]:
        events: list[ConflictEvent] = []
        now = datetime.now(timezone.utc)
        for source_name, fetch_fn in SOURCES.items():
            try:
                raw = fetch_fn()
                normalized = self._normalize(source_name, raw, now)
                events.extend(normalized)
                logger.info("Source %s returned %d events", source_name, len(normalized))
            except Exception:
                logger.exception("Source %s failed, skipping", source_name)
        return events

    def _normalize(
        self,
        source_name: str,
        raw_events: list,
        fetched_at: datetime,
    ) -> list[ConflictEvent]:
        results: list[ConflictEvent] = []
        for event in raw_events:
            # Skip events without valid coordinates.
            lat = getattr(event, "latitude", None)
            lon = getattr(event, "longitude", None)
            if lat is None or lon is None:
                continue
            if lat == 0.0 and lon == 0.0:
                continue

            raw_id = getattr(event, "id", None)
            if raw_id is not None:
                source_id = str(raw_id)
            else:
                # Some sources (e.g. Texty) return id=None for every event.
                # Generate a stable synthetic ID from the event's unique attributes
                # so dedup works correctly across fetches.
                hash_input = f"{source_name}:{lat}:{lon}:{getattr(event, 'date', '')}:{getattr(event, 'title', '')}"
                source_id = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

            results.append(
                ConflictEvent(
                    source_id=source_id,
                    source=source_name,
                    title=getattr(event, "title", "") or "",
                    description=getattr(event, "description", "") or "",
                    latitude=float(lat),
                    longitude=float(lon),
                    event_date=getattr(event, "date", None),
                    place_desc=getattr(event, "place_desc", "") or "",
                    links=getattr(event, "links", []) or [],
                    fetched_at=fetched_at,
                )
            )
        return results

    def source_name(self) -> str:
        return "osint_geo"
