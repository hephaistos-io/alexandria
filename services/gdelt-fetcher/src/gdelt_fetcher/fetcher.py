"""Fetches geolocated conflict events from GDELT 2.0 Event exports.

GDELT publishes a new export every 15 minutes as a tab-separated CSV inside a
ZIP file. We poll the ``lastupdate.txt`` endpoint to find the most recent file,
download it, parse the rows, and filter for armed conflict events using CAMEO
event codes.

CAMEO filtering:
    Root codes 18 (Assault), 19 (Fight), 20 (Mass Violence) cover armed attacks,
    military operations, bombings, airstrikes, and unconventional mass violence.
    Base code 145 (Violent Protest) captures riots and violent demonstrations.

    We do NOT use QuadClass == 4 (Material Conflict) because it also includes
    root code 17 (Coerce) — arrests, curfews, property seizure — which are not
    armed conflict events.

Column positions reference the GDELT 2.0 Event Database codebook. The files
have no header row; columns are strictly positional.
"""

import csv
import io
import logging
import zipfile
from datetime import datetime, timezone

import httpx

from gdelt_fetcher.models import ConflictEvent

logger = logging.getLogger(__name__)

# GDELT 2.0 endpoints — no authentication required.
LAST_UPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"

# Column indices in the GDELT 2.0 export TSV (0-indexed).
COL_GLOBAL_EVENT_ID = 0
COL_SQLDATE = 1  # YYYYMMDD
COL_ACTOR1_NAME = 6
COL_ACTOR2_NAME = 16
COL_EVENT_CODE = 26  # full CAMEO code — MUST be treated as string
COL_EVENT_BASE_CODE = 27
COL_EVENT_ROOT_CODE = 28
COL_GOLDSTEIN_SCALE = 30
COL_NUM_MENTIONS = 31
COL_NUM_SOURCES = 32
COL_ACTION_GEO_FULLNAME = 52
COL_ACTION_GEO_LAT = 56
COL_ACTION_GEO_LONG = 57
COL_SOURCE_URL = 60

# CAMEO root codes for armed conflict events.
CONFLICT_ROOT_CODES = {"18", "19", "20"}

# CAMEO base code for violent protests (sub-tree of root code 14).
CONFLICT_BASE_CODES = {"145"}

# Human-readable descriptions for CAMEO root/base codes, used to build event
# titles. These are abbreviated from the full CAMEO manual.
CAMEO_DESCRIPTIONS: dict[str, str] = {
    "145": "Violent protest",
    "180": "Unconventional violence",
    "181": "Abduction / hostage-taking",
    "182": "Physical assault",
    "183": "Bombing",
    "184": "Use as human shield",
    "185": "Assassination attempt",
    "186": "Assassination",
    "190": "Military force",
    "191": "Military blockade",
    "192": "Territory occupation",
    "193": "Small arms / light weapons",
    "194": "Artillery / tank fire",
    "195": "Aerial weapons",
    "196": "Ceasefire violation",
    "200": "Unconventional mass violence",
    "201": "Mass expulsion",
    "202": "Mass killing",
    "203": "Ethnic cleansing",
    "204": "Weapons of mass destruction",
    # Root-level fallbacks (used when the base code isn't in the map).
    "18": "Assault",
    "19": "Armed conflict",
    "20": "Mass violence",
    "14": "Protest",
}


def _is_conflict_event(root_code: str, base_code: str) -> bool:
    """Return True if the CAMEO codes indicate an armed conflict event."""
    return root_code in CONFLICT_ROOT_CODES or base_code in CONFLICT_BASE_CODES


def _build_title(actor1: str, actor2: str, base_code: str, root_code: str) -> str:
    """Build a human-readable title from GDELT actor names and CAMEO codes.

    Examples:
        "ISRAEL — Aerial weapons — IRAN"
        "Aerial weapons — GAZA"
        "Armed conflict — Kyiv, Ukraine"
    """
    action = CAMEO_DESCRIPTIONS.get(base_code) or CAMEO_DESCRIPTIONS.get(root_code, "Conflict")
    parts = []
    if actor1:
        parts.append(actor1)
    parts.append(action)
    if actor2:
        parts.append(actor2)
    return " — ".join(parts)


def _parse_date(sqldate: str) -> datetime | None:
    """Parse GDELT's YYYYMMDD date into a timezone-aware datetime."""
    if not sqldate or len(sqldate) != 8:
        return None
    try:
        return datetime.strptime(sqldate, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class GdeltFetcher:
    """Downloads the latest GDELT export and extracts conflict events."""

    def __init__(self) -> None:
        self._client = httpx.Client(timeout=30.0)

    def fetch(self) -> list[ConflictEvent]:
        """Fetch the most recent GDELT export and return conflict events."""
        export_url = self._get_latest_export_url()
        if not export_url:
            return []

        raw_tsv = self._download_export(export_url)
        if not raw_tsv:
            return []

        now = datetime.now(timezone.utc)
        events = self._parse_events(raw_tsv, now)
        logger.info("GDELT export yielded %d conflict events (from %s)", len(events), export_url)
        return events

    def _get_latest_export_url(self) -> str | None:
        """Poll lastupdate.txt to find the URL of the most recent export file."""
        try:
            resp = self._client.get(LAST_UPDATE_URL)
            resp.raise_for_status()
        except httpx.HTTPError:
            logger.exception("Failed to fetch GDELT lastupdate.txt")
            return None

        # lastupdate.txt has 3 lines: export, mentions, gkg.
        # Format: "<size> <md5> <url>"
        # We want the first line (the .export.CSV.zip file).
        for line in resp.text.strip().splitlines():
            parts = line.strip().split()
            if len(parts) == 3 and ".export.CSV.zip" in parts[2]:
                return parts[2]

        logger.error("No export URL found in lastupdate.txt")
        return None

    def _download_export(self, url: str) -> str | None:
        """Download a GDELT export ZIP and return the CSV content as a string."""
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError:
            logger.exception("Failed to download GDELT export: %s", url)
            return None

        try:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                # Each ZIP contains exactly one CSV file.
                csv_name = zf.namelist()[0]
                return zf.read(csv_name).decode("ascii", errors="replace")
        except (zipfile.BadZipFile, IndexError, KeyError):
            logger.exception("Failed to extract GDELT export ZIP: %s", url)
            return None

    def _parse_events(self, tsv_content: str, fetched_at: datetime) -> list[ConflictEvent]:
        """Parse the TSV content and filter for conflict events with valid coords."""
        events: list[ConflictEvent] = []

        reader = csv.reader(io.StringIO(tsv_content), delimiter="\t")
        for row in reader:
            # GDELT exports have 61 columns. Skip malformed rows.
            if len(row) < 61:
                continue

            root_code = row[COL_EVENT_ROOT_CODE].strip()
            base_code = row[COL_EVENT_BASE_CODE].strip()

            if not _is_conflict_event(root_code, base_code):
                continue

            # Parse coordinates — skip events without valid geo.
            try:
                lat = float(row[COL_ACTION_GEO_LAT])
                lon = float(row[COL_ACTION_GEO_LONG])
            except (ValueError, IndexError):
                continue

            # Skip (0, 0) coordinates — GDELT uses these as "unknown location".
            if lat == 0.0 and lon == 0.0:
                continue

            actor1 = row[COL_ACTOR1_NAME].strip()
            actor2 = row[COL_ACTOR2_NAME].strip()
            place = row[COL_ACTION_GEO_FULLNAME].strip()
            source_url = row[COL_SOURCE_URL].strip()

            # Extract country from the full place name.  GDELT uses
            # "City, State, Country" format — the last comma segment is
            # the country.  Single-segment names are already country-level.
            country = place.rsplit(",", 1)[-1].strip() if place else ""

            events.append(
                ConflictEvent(
                    source_id=row[COL_GLOBAL_EVENT_ID].strip(),
                    source="gdelt",
                    title=_build_title(actor1, actor2, base_code, root_code),
                    description=f"Goldstein: {row[COL_GOLDSTEIN_SCALE].strip()}, "
                    f"Mentions: {row[COL_NUM_MENTIONS].strip()}, "
                    f"Sources: {row[COL_NUM_SOURCES].strip()}",
                    latitude=lat,
                    longitude=lon,
                    event_date=_parse_date(row[COL_SQLDATE].strip()),
                    country=country,
                    place_desc=place,
                    links=[source_url] if source_url else [],
                    fetched_at=fetched_at,
                )
            )

        return events

    def source_name(self) -> str:
        return "gdelt"
