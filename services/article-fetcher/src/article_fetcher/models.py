from dataclasses import dataclass
from datetime import datetime


@dataclass
class Article:
    """A fetched article from an external source."""

    source: str  # feed type, e.g. "rss", "api"
    origin: str  # news outlet identifier, e.g. "bbc_world", "ap"
    title: str
    url: str
    summary: str
    published: datetime | None  # when the source published it (may be unknown)
    fetched_at: datetime  # when we pulled it
