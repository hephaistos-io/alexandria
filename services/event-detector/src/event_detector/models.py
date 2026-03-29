"""Data models for the event detector."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ArticleRow:
    """A row from the articles table with the fields we need for clustering."""

    id: int
    title: str
    entities: list[dict]
    automatic_labels: list[str] | None
    published_at: datetime | None


@dataclass
class ConflictRow:
    """A row from the conflict_events table."""

    id: int
    latitude: float
    longitude: float
    event_date: datetime | None
    country: str | None


@dataclass
class ExistingEvent:
    """An event already stored in the database."""

    id: int
    slug: str
    title: str
    status: str
    heat: float
    entity_qids: list[str]
    centroid_lat: float | None
    centroid_lng: float | None
    first_seen: datetime
    last_seen: datetime


@dataclass
class DetectedEvent:
    """A newly detected or updated event ready to be written to the database."""

    slug: str
    title: str
    status: str
    heat: float
    entity_qids: list[str]
    centroid_lat: float | None
    centroid_lng: float | None
    first_seen: datetime
    last_seen: datetime
    article_ids: list[int] = field(default_factory=list)
    conflict_ids: list[int] = field(default_factory=list)
    existing_id: int | None = None
