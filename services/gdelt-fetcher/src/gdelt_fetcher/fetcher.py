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
import math
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
COL_ACTOR1_GEO_FULLNAME = 36
COL_ACTOR1_GEO_LAT = 40
COL_ACTOR1_GEO_LONG = 41
COL_ACTOR2_GEO_FULLNAME = 44
COL_ACTOR2_GEO_LAT = 48
COL_ACTOR2_GEO_LONG = 49
COL_ACTION_GEO_FULLNAME = 52
COL_ACTION_GEO_LAT = 56
COL_ACTION_GEO_LONG = 57
COL_SOURCE_URL = 60

# Max allowed distance (km) between our chosen coordinate and the nearest
# corroborating geo point. 2000 km covers every regional conflict we care
# about (Iran-Israel at ~1600 km is the widest) while rejecting obvious
# dateline leaks like "TEHRAN attacks ISRAEL" geocoded to Geneva (~3800 km
# from Tehran). See the geo-resolution discussion in fetcher docstring.
GEO_SANITY_THRESHOLD_KM = 2000.0

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


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lng) points, in kilometres.

    Standard haversine formula. Earth radius 6371 km gives ~0.5% accuracy —
    more than enough for a 2000 km sanity check.
    """
    lat1, lng1 = a
    lat2, lng2 = b
    # Convert to radians once.
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def _parse_coord(lat_str: str, lng_str: str) -> tuple[float, float] | None:
    """Parse a (lat, lng) pair from raw column strings.

    Returns None for empty, non-numeric, or (0, 0) values. GDELT uses (0, 0)
    as a sentinel for "location unknown", so we treat it the same as missing.
    Strips whitespace so the caller doesn't need to remember to.
    """
    lat_str = lat_str.strip()
    lng_str = lng_str.strip()
    if not lat_str or not lng_str:
        return None
    try:
        lat = float(lat_str)
        lng = float(lng_str)
    except ValueError:
        return None
    if lat == 0.0 and lng == 0.0:
        return None
    return (lat, lng)


# CAMEO root codes where Actor2 is a concrete territorial target (the thing
# that got hit), so Actor2Geo is usually the real location of the action.
# For other codes — notably violent protest (root 14), where Actor2 is
# typically an abstract entity like "GOVERNMENT" geocoded to the capital —
# we skip Actor2Geo to avoid systematically routing events to capital cities.
_ACTOR2_AS_TARGET_ROOT_CODES = frozenset({"18", "19", "20"})


def _resolve_geo(
    actor1: tuple[float, float] | None,
    actor2: tuple[float, float] | None,
    action: tuple[float, float] | None,
    actor1_place: str,
    actor2_place: str,
    action_place: str,
    root_code: str,
    threshold_km: float = GEO_SANITY_THRESHOLD_KM,
) -> tuple[tuple[float, float], str] | None:
    """Pick a sane coordinate for a GDELT event.

    GDELT publishes three independent geo columns per event: where Actor1 is,
    where Actor2 is, and where the article text places the action. The third
    is unreliable because GDELT's geocoder latches onto the most prominent
    place name near the event sentence — which is often the article's
    dateline (Geneva, New York, Washington), not the site of violence.

    Strategy:
      1. Build a priority-ordered candidate list. For armed-conflict root
         codes (18/19/20) we prefer Actor2Geo first because Actor2 is the
         target of the action. For protests (root 14) and other codes where
         Actor2 tends to be an abstract entity, we drop Actor2Geo from the
         preference chain entirely — Actor1Geo (the protesters) is a better
         signal than the capital city Actor2 usually geocodes to.
      2. Walk the candidates in order. For each candidate, check that it's
         within ``threshold_km`` of at least one OTHER populated geo column.
         The first candidate that passes wins. We don't commit to the top
         priority and give up — a polluted top candidate shouldn't force us
         to drop an event that the lower candidates would validate.
      3. If only one geo column is populated, we have nothing to validate
         against, so we trust it. This is a deliberate tradeoff: without it,
         we'd throw out huge volumes of legitimate events where GDELT only
         populated ActionGeo.

    Returns ``(coords, place_desc)`` for the chosen geo, or ``None`` if the
    event has no usable geography or no candidate passes sanity-checking.
    """
    # Build priority-ordered list. Actor2Geo is only a preferred candidate
    # for the root codes where Actor2 represents a concrete territorial
    # target — see _ACTOR2_AS_TARGET_ROOT_CODES for the rationale.
    priority: list[tuple[tuple[float, float] | None, str]]
    if root_code in _ACTOR2_AS_TARGET_ROOT_CODES:
        priority = [
            (actor2, actor2_place),
            (actor1, actor1_place),
            (action, action_place),
        ]
    else:
        priority = [
            (actor1, actor1_place),
            (action, action_place),
            (actor2, actor2_place),
        ]

    candidates: list[tuple[tuple[float, float], str]] = [
        (coord, place) for coord, place in priority if coord is not None
    ]

    if not candidates:
        return None

    # If there's only one signal, we can't cross-check. Trust it.
    if len(candidates) == 1:
        return candidates[0]

    # Walk candidates in priority order and return the first one that passes
    # the sanity check. "At least one" agreement (not "all") because the
    # contradicting column is exactly the noise we're trying to detect.
    for i, (chosen, chosen_place) in enumerate(candidates):
        others = [c for j, (c, _) in enumerate(candidates) if j != i]
        if any(_haversine_km(chosen, other) <= threshold_km for other in others):
            return (chosen, chosen_place)

    return None


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

            # Resolve geography: prefer Actor2Geo → Actor1Geo → ActionGeo,
            # and sanity-check the chosen point against the others so dateline
            # leaks (article filed in Geneva about fighting in the Middle East)
            # don't plant a marker in Switzerland.
            actor1_geo = _parse_coord(row[COL_ACTOR1_GEO_LAT], row[COL_ACTOR1_GEO_LONG])
            actor2_geo = _parse_coord(row[COL_ACTOR2_GEO_LAT], row[COL_ACTOR2_GEO_LONG])
            action_geo = _parse_coord(row[COL_ACTION_GEO_LAT], row[COL_ACTION_GEO_LONG])

            resolved = _resolve_geo(
                actor1=actor1_geo,
                actor2=actor2_geo,
                action=action_geo,
                actor1_place=row[COL_ACTOR1_GEO_FULLNAME].strip(),
                actor2_place=row[COL_ACTOR2_GEO_FULLNAME].strip(),
                action_place=row[COL_ACTION_GEO_FULLNAME].strip(),
                root_code=root_code,
            )
            if resolved is None:
                continue

            (lat, lon), place = resolved

            actor1 = row[COL_ACTOR1_NAME].strip()
            actor2 = row[COL_ACTOR2_NAME].strip()
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
