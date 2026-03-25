"""Resolve entity mentions to Wikidata QIDs, with Redis caching."""

import json
import logging
import threading
import time

import httpx
import redis

logger = logging.getLogger(__name__)

CACHE_TTL = 7 * 24 * 60 * 60  # 7 days
CACHE_NONE_SENTINEL = "__NONE__"

# spaCy NER label types that are worth looking up on Wikidata.
# Types like CARDINAL ("at least 18"), QUANTITY ("4,000 km"), DATE, TIME,
# PERCENT, MONEY, and ORDINAL are numeric/temporal — Wikidata can't
# meaningfully resolve them, and they waste API quota.
RESOLVABLE_LABELS = frozenset({
    "PERSON",      # People
    "ORG",         # Organizations
    "GPE",         # Geopolitical entities (countries, cities)
    "LOC",         # Non-GPE locations (mountains, bodies of water)
    "NORP",        # Nationalities, religious groups, political groups
    "EVENT",       # Named events (wars, elections)
    "FAC",         # Facilities (airports, buildings)
    "WORK_OF_ART", # Titles of books, songs, etc.
    "LAW",         # Named laws and treaties
    "PRODUCT",     # Named products
    "LANGUAGE",    # Named languages
})

# spaCy NER label types that represent geographic locations.
# For these we make a second API call to fetch P625 (coordinate location) from Wikidata.
LOCATION_LABELS = frozenset({"GPE", "LOC", "FAC"})

# Wikidata QIDs that represent Wikimedia internal pages, not real-world entities.
# If an item's P31 ("instance of") includes any of these, we skip it.
WIKIMEDIA_INTERNAL_QIDS = frozenset({
    "Q4167836",   # Wikimedia category
    "Q4167410",   # Wikimedia disambiguation page
    "Q11266439",  # Wikimedia template
    "Q13406463",  # Wikimedia list article
    "Q17362920",  # Wikimedia duplicated page
})

# Rate limiting: base delay between API calls and retry behaviour on 429.
_BASE_DELAY = 0.2           # 200ms between requests (5 req/s steady state)
_MAX_RETRIES = 3            # retry up to 3 times on 429
_FALLBACK_RETRY_DELAY = 10  # seconds — used only if Retry-After header is absent

# OAuth2 token refresh: fetch a new JWT 10 minutes before expiry.
_TOKEN_REFRESH_MARGIN = 600  # seconds
_TOKEN_ENDPOINT = "https://meta.wikimedia.org/w/rest.php/oauth2/access_token"

_USER_AGENT = "AlexandriaBot/1.0 (https://github.com/risi/alexandria; OSINT pipeline)"


class RateLimitedError(Exception):
    """Raised when Wikidata rate-limits us and all retries are exhausted."""


class WikimediaAuth:
    """Handles OAuth2 client-credentials flow for the Wikimedia API.

    Wikimedia's API portal issues a client_id and client_secret for
    server-side apps.  These are exchanged for a short-lived JWT
    (4 hours) via a POST to meta.wikimedia.org.  This class manages
    the token lifecycle — initial fetch and automatic refresh before
    expiry — so the resolver always has a valid Bearer token.

    Note: the client-credentials grant does NOT return a refresh token.
    We simply re-authenticate with the same credentials when the JWT
    is about to expire.
    """

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token: str | None = None
        self._expires_at: float = 0  # epoch seconds
        self._lock = threading.Lock()
        # Separate client for token requests — the resolver's client
        # carries the Bearer header which we don't have yet at init time.
        self._http = httpx.Client(
            headers={"User-Agent": _USER_AGENT},
            timeout=15.0,
        )

    def get_token(self) -> str:
        """Return a valid access token, refreshing if needed.

        Thread-safe: uses a lock so concurrent resolve() calls don't
        all race to refresh at the same time.
        """
        with self._lock:
            if self._access_token and time.time() < self._expires_at:
                return self._access_token
            return self._refresh()

    def _refresh(self) -> str:
        """Exchange client credentials for a new JWT access token."""
        logger.info("Requesting new Wikimedia OAuth2 access token")
        resp = self._http.post(
            _TOKEN_ENDPOINT,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        self._access_token = body["access_token"]
        # expires_in is typically 14400 (4 hours). Refresh 10 min early
        # so we never send a request with an about-to-expire token.
        expires_in = body.get("expires_in", 14400)
        self._expires_at = time.time() + expires_in - _TOKEN_REFRESH_MARGIN
        logger.info(
            "Obtained Wikimedia access token (expires in %ds, will refresh in %ds)",
            expires_in,
            expires_in - _TOKEN_REFRESH_MARGIN,
        )
        return self._access_token

    def close(self) -> None:
        self._http.close()


class WikidataResolver:
    """Resolves entity mentions to Wikidata entries via the Wikibase REST API.

    Uses the newer REST endpoints instead of the legacy Action API (api.php):
      - Search: GET /w/rest.php/wikibase/v0/search/items?q=...&language=en
      - Statements: GET /w/rest.php/wikibase/v1/entities/items/{QID}/statements

    Results are cached in Redis to avoid hammering Wikidata on repeated mentions.
    Cache entries are either a JSON object or the sentinel string "__NONE__" for
    confirmed misses (i.e. Wikidata returned no results). Both expire after 7 days.

    Redis failures are non-fatal: a read failure falls through to the API, a write
    failure just means the result is not cached for next time.

    Rate limiting: a 200ms base delay between requests, plus server-guided
    retry on HTTP 429 responses.  When Wikidata returns a Retry-After header,
    we sleep for exactly that duration.  If the header is absent, we fall back
    to a fixed 10s delay.  Retries are capped at 3 per entity lookup.

    Authentication (two methods, in priority order):

    1. Personal API token (WIKIDATA_API_TOKEN) — simplest.  A static Bearer
       token created at api.wikimedia.org.  Never expires.  5,000 req/hr.
    2. OAuth2 client credentials (WIKIDATA_CLIENT_ID + WIKIDATA_CLIENT_SECRET) —
       exchanges credentials for a short-lived JWT (4 hours).  Same rate limit.
    3. Neither — falls back to unauthenticated access (~500 req/hr).
    """

    # Wikibase REST API base — search is v0, entity/statement endpoints are v1.
    _SEARCH_URL = "https://www.wikidata.org/w/rest.php/wikibase/v0/search/items"
    _STATEMENTS_URL = "https://www.wikidata.org/w/rest.php/wikibase/v1/entities/items"

    def __init__(
        self,
        redis_url: str,
        api_token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._redis = redis.from_url(redis_url)
        # Verify Redis is reachable at startup rather than failing on first message.
        self._redis.ping()
        logger.info("Redis connection verified")

        # Resolve authentication method in priority order.
        self._static_token: str | None = None
        self._auth: WikimediaAuth | None = None

        if api_token:
            # Simplest path: a personal API token that never expires.
            self._static_token = api_token
            logger.info("Using personal API token for Wikimedia authentication")
        elif client_id and client_secret:
            # OAuth2 client-credentials: exchange for a JWT at startup.
            self._auth = WikimediaAuth(client_id, client_secret)
            try:
                self._auth.get_token()
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "Failed to obtain Wikimedia access token: %s — "
                    "falling back to unauthenticated access",
                    exc.response.text,
                )
                self._auth = None
        else:
            logger.warning(
                "No Wikimedia credentials set — using unauthenticated access "
                "(~500 req/hr). Set WIKIDATA_API_TOKEN or WIKIDATA_CLIENT_ID + "
                "WIKIDATA_CLIENT_SECRET for 5,000 req/hr."
            )

        self._http = httpx.Client(
            headers={"User-Agent": _USER_AGENT},
            timeout=10.0,
        )

    def _request_headers(self) -> dict[str, str]:
        """Build per-request headers, including a fresh Bearer token if available."""
        if self._static_token:
            return {"Authorization": f"Bearer {self._static_token}"}
        if self._auth:
            return {"Authorization": f"Bearer {self._auth.get_token()}"}
        return {}

    def _fetch_coordinates(self, qid: str) -> tuple[float, float] | None:
        """Fetch geographic coordinates for a Wikidata entity via the P625 statement.

        Uses the Wikibase REST API v1 statements endpoint, which returns a much
        cleaner structure than the old Action API:
            GET /wikibase/v1/entities/items/{QID}/statements?property=P625

        P625 is the "coordinate location" property. Not all entities have it —
        we return None if the statement is absent or the API call fails.
        """
        time.sleep(_BASE_DELAY)
        try:
            resp = self._http.get(
                f"{self._STATEMENTS_URL}/{qid}/statements",
                params={"property": "P625"},
                headers=self._request_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            # Response: {"P625": [{"value": {"content": {"latitude": ..., "longitude": ...}}}]}
            value = data["P625"][0]["value"]["content"]
            return (value["latitude"], value["longitude"])
        except (httpx.HTTPError, KeyError, IndexError, ValueError):
            logger.debug("No P625 coordinates for %s", qid)
            return None

    def _is_wikimedia_internal(self, qid: str) -> bool:
        """Check if a Wikidata item is a Wikimedia internal page (category, disambiguation, etc.).

        Fetches the P31 ("instance of") statements for the item and checks
        whether any of them match known Wikimedia-internal QIDs. This costs
        one extra API call per cache miss, but prevents junk like
        "Category:Works by Indian people" from entering the knowledge graph.
        """
        time.sleep(_BASE_DELAY)
        try:
            resp = self._http.get(
                f"{self._STATEMENTS_URL}/{qid}/statements",
                params={"property": "P31"},
                headers=self._request_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            # Response shape: {"P31": [{"value": {"content": "Q5"}}, ...]}
            for statement in data.get("P31", []):
                instance_qid = statement.get("value", {}).get("content")
                if instance_qid in WIKIMEDIA_INTERNAL_QIDS:
                    logger.info(
                        "Skipping %s — instance of Wikimedia internal item %s",
                        qid, instance_qid,
                    )
                    return True
            return False
        except (httpx.HTTPError, KeyError, IndexError, ValueError):
            # If the check fails, let the entity through — better to have a
            # questionable entity than to drop a valid one.
            logger.debug("P31 check failed for %s, allowing", qid)
            return False

    def resolve(self, mention: str, label: str | None = None) -> dict | None:
        """Return {"wikidata_id": "Q794", "label": "Iran", "description": "..."} or None.

        Args:
            mention: The entity text to look up (e.g. "Iran").
            label:   The spaCy NER label (e.g. "GPE", "CARDINAL"). If provided
                     and not in RESOLVABLE_LABELS, the lookup is skipped entirely.
        """
        # Skip non-resolvable entity types (CARDINAL, QUANTITY, DATE, etc.)
        if label is not None and label not in RESOLVABLE_LABELS:
            return None

        key = f"entity:{mention.lower().strip()}:{label or ''}"

        # 1. Check cache — may return None on miss or Redis failure
        cached = self._redis_get(key)
        if cached is not None:
            return None if cached == CACHE_NONE_SENTINEL else json.loads(cached)

        # 2. Cache miss — call Wikidata with rate limiting.
        # RateLimitedError is NOT caught here — it propagates to the caller
        # so the message handler can re-enqueue the article for retry.
        # This also ensures rate-limit failures are never cached.
        time.sleep(_BASE_DELAY)
        result = self._search(mention, label=label)

        # 3. Cache the result (or the sentinel) for future lookups.
        # Only genuine "not found" responses are cached as NONE.
        self._redis_set(key, json.dumps(result) if result else CACHE_NONE_SENTINEL)
        return result

    def _parse_retry_after(self, resp: httpx.Response) -> float:
        """Extract the delay from a Retry-After header, or fall back to default.

        The header can be either a number of seconds ("120") or an HTTP-date.
        We only handle the numeric form — Wikidata uses seconds in practice.
        """
        raw = resp.headers.get("Retry-After")
        if raw is not None:
            try:
                return max(float(raw), 1.0)  # at least 1s to avoid busy-loop
            except ValueError:
                pass
        return _FALLBACK_RETRY_DELAY

    def _search(self, mention: str, label: str | None = None) -> dict | None:
        """Query Wikibase REST API search endpoint, return the top result or None.

        Uses: GET /wikibase/v0/search/items?q=...&language=en&limit=1

        The response format differs from the old Action API:
            {"results": [{"id": "Q794", "display-label": {"value": "Iran"},
                          "description": {"value": "country in Western Asia"}}]}

        For location entity types (GPE, LOC, FAC), also fetches P625 geographic
        coordinates via the v1 statements endpoint.

        Retries up to _MAX_RETRIES times on HTTP 429 (Too Many Requests),
        using the server's Retry-After header to determine the wait duration.
        """
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = self._http.get(
                    self._SEARCH_URL,
                    params={
                        "q": mention,
                        "language": "en",
                        "limit": "1",
                    },
                    headers=self._request_headers(),
                )
                if resp.status_code == 429:
                    if attempt < _MAX_RETRIES:
                        delay = self._parse_retry_after(resp)
                        logger.info(
                            "Rate limited by Wikidata (Retry-After: %.0fs), "
                            "waiting (attempt %d/%d)",
                            delay, attempt + 1, _MAX_RETRIES,
                        )
                        time.sleep(delay)
                        continue
                    else:
                        logger.warning(
                            "Rate limited by Wikidata for '%s' after %d retries, giving up",
                            mention, _MAX_RETRIES,
                        )
                        raise RateLimitedError(mention)

                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])
                if not results:
                    return None
                top = results[0]
                qid = top["id"]

                # Filter out Wikimedia internal pages (categories, disambiguation, etc.)
                # This prevents junk like "Category:Works by Indian people" from
                # entering the knowledge graph as if it were a real entity.
                if self._is_wikimedia_internal(qid):
                    return None

                # REST API nests label and description in sub-objects.
                display_label = top.get("display-label", {})
                description_obj = top.get("description", {})

                # Fetch coordinates for location-type entities only.
                latitude: float | None = None
                longitude: float | None = None
                if label in LOCATION_LABELS:
                    coords = self._fetch_coordinates(qid)
                    if coords is not None:
                        latitude, longitude = coords

                return {
                    "wikidata_id": qid,
                    "label": display_label.get("value", mention),
                    "description": (
                        description_obj.get("value", "")
                        if isinstance(description_obj, dict)
                        else ""
                    ),
                    "latitude": latitude,
                    "longitude": longitude,
                }
            except (httpx.HTTPError, KeyError, ValueError):
                logger.warning("Wikidata lookup failed for '%s'", mention, exc_info=True)
                return None
        return None

    def _redis_get(self, key: str) -> str | None:
        """Fetch a cache entry. Returns None on miss or Redis failure."""
        try:
            val = self._redis.get(key)
            # redis-py returns bytes for string values — decode to str
            return val.decode() if isinstance(val, bytes) else val
        except redis.RedisError:
            logger.warning("Redis read failed, falling through to API")
            return None

    def _redis_set(self, key: str, value: str) -> None:
        """Write a cache entry with TTL. Logs a warning on failure but does not raise."""
        try:
            self._redis.set(key, value, ex=CACHE_TTL)
        except redis.RedisError:
            logger.warning("Redis write failed, result not cached")

    def close(self) -> None:
        """Close the underlying HTTP client and auth client."""
        self._http.close()
        if self._auth:
            self._auth.close()
