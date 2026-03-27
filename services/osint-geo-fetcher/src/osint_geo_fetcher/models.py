from dataclasses import dataclass
from datetime import datetime


@dataclass
class ConflictEvent:
    """A geolocated armed conflict event from an OSINT source."""

    source_id: str  # unique ID from upstream source
    source: str  # "bellingcat", "geoconfirmed", "texty", "defmon", "ceninfores"
    title: str
    description: str
    latitude: float
    longitude: float
    event_date: datetime | None
    place_desc: str
    links: list[str]
    fetched_at: datetime
