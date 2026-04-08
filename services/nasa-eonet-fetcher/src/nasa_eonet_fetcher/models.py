from dataclasses import dataclass
from datetime import datetime


@dataclass
class NaturalDisaster:
    """A geolocated natural disaster event from NASA EONET.

    Mirrors the shape of `ConflictEvent` from the conflict fetchers so the
    downstream consumer/storage layer follows the same patterns, with a few
    EONET-specific fields:

    - `category`         comma-joined EONET category ids (e.g. "wildfires" or
                         "wildfires,severeStorms" when an event spans more
                         than one). Comma-joined rather than a list because
                         the storage table uses TEXT (not TEXT[]) — most events
                         have a single category and a TEXT column is cheaper
                         to filter on.
    - `geometry_type`    "Point" or "Polygon" — recorded so the consumer/UI
                         knows whether the lat/lng is a true location or a
                         centroid we computed from polygon vertices.
    - `closed_at`        non-null when EONET marks the event as ended.
    - `magnitude_value`  optional, category-dependent (e.g. fire size in acres,
                         storm wind speed). Lives on the *geometry* in EONET's
                         schema, not on the event itself — we copy the latest
                         observation's value into this scalar column for cheap
                         filtering and to drive marker sizing on the map.
                         Unit is in `magnitude_unit`.
    - `geometries`       full EONET geometry array, stored verbatim as JSONB.
                         Each entry is a `{date, type, coordinates,
                         magnitudeValue?, magnitudeUnit?}` dict. Keeping the
                         whole timeline lets the frontend animate storm
                         tracks or wildfire growth without a schema change.
                         For "where is this on the map right now" the scalar
                         lat/lng/event_date columns are still authoritative.
    """

    source_id: str  # EONET event id (stable across fetches)
    source: str  # always "nasa_eonet"
    title: str
    description: str | None
    category: str
    latitude: float
    longitude: float
    geometry_type: str  # "Point" | "Polygon"
    event_date: datetime | None  # date of the latest geometry observation
    closed_at: datetime | None
    magnitude_value: float | None
    magnitude_unit: str | None
    links: list[str]
    fetched_at: datetime
    geometries: list[dict]  # full EONET geometry array, stored as JSONB
