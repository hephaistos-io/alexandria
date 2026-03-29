from dataclasses import dataclass
from datetime import datetime


@dataclass
class ConflictEvent:
    """A geolocated armed conflict event from GDELT."""

    source_id: str  # GlobalEventID from GDELT (stored as string, not int)
    source: str  # always "gdelt"
    title: str  # constructed from actors + event description
    description: str
    latitude: float
    longitude: float
    event_date: datetime | None
    country: str
    place_desc: str
    links: list[str]  # SOURCEURL from GDELT
    fetched_at: datetime
