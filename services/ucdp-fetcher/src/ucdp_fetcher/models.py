from dataclasses import dataclass
from datetime import datetime


@dataclass
class ConflictEvent:
    """A geolocated armed conflict event from an OSINT source."""

    source_id: str  # unique ID from upstream source
    source: str  # "ucdp"
    title: str
    description: str
    latitude: float
    longitude: float
    event_date: datetime | None
    country: str
    place_desc: str
    links: list[str]
    fetched_at: datetime
