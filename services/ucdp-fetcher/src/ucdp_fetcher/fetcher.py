"""Fetches conflict events from the UCDP Candidate Events API."""

import logging
from datetime import datetime, timezone

import httpx

from ucdp_fetcher.models import ConflictEvent

logger = logging.getLogger(__name__)

API_BASE = "https://ucdpapi.pcr.uu.se/api/gedcandidate/26.0.2"
DEFAULT_PAGE_SIZE = 1000


class UcdpFetcher:
    """Fetches conflict events from the UCDP GED Candidate dataset."""

    def __init__(self, access_token: str) -> None:
        self._token = access_token

    def fetch(self) -> list[ConflictEvent]:
        """Fetch all pages of events from UCDP."""
        events: list[ConflictEvent] = []
        page = 1
        now = datetime.now(timezone.utc)

        while True:
            url = f"{API_BASE}?pagesize={DEFAULT_PAGE_SIZE}&page={page}"
            logger.info("Fetching UCDP page %d", page)

            try:
                response = httpx.get(
                    url,
                    headers={"x-ucdp-access-token": self._token},
                    timeout=60.0,
                )
                response.raise_for_status()
            except httpx.HTTPError:
                logger.exception("UCDP API request failed on page %d", page)
                break

            data = response.json()
            results = data.get("Result", [])
            if not results:
                break

            for item in results:
                event = self._normalize(item, now)
                if event is not None:
                    events.append(event)

            total_pages = data.get("TotalPages", 1)
            if page >= total_pages:
                break
            page += 1

        logger.info("UCDP returned %d events total", len(events))
        return events

    def _normalize(self, item: dict, fetched_at: datetime) -> ConflictEvent | None:
        """Convert a UCDP API result dict to a ConflictEvent."""
        lat = item.get("latitude")
        lon = item.get("longitude")
        if lat is None or lon is None:
            return None
        if lat == 0.0 and lon == 0.0:
            return None

        # Build a descriptive title from actors and violence type.
        side_a = item.get("side_a", "Unknown")
        side_b = item.get("side_b", "Unknown")
        violence_type = {1: "State-based", 2: "Non-state", 3: "One-sided"}.get(
            item.get("type_of_violence"), "Unknown"
        )
        title = f"{violence_type}: {side_a} vs {side_b}"

        # Build description with fatality info.
        best = item.get("best", 0)
        country = item.get("country", "")
        description = f"{violence_type} violence in {country}. Estimated fatalities: {best}."

        # Parse date.
        date_str = item.get("date_start")
        event_date = None
        if date_str:
            try:
                event_date = datetime.fromisoformat(date_str)
            except (ValueError, TypeError):
                pass

        return ConflictEvent(
            source_id=str(item.get("id", "")),
            source="ucdp",
            title=title,
            description=description,
            latitude=float(lat),
            longitude=float(lon),
            event_date=event_date,
            place_desc=item.get("where_description", "") or "",
            links=[],
            fetched_at=fetched_at,
        )

    def source_name(self) -> str:
        return "ucdp"
