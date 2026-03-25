"""Tests for WikidataResolver — all external I/O is mocked."""

import json
from unittest.mock import MagicMock, patch

import httpx
import redis

from entity_resolver.resolver import CACHE_NONE_SENTINEL, CACHE_TTL, WikidataResolver

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

IRAN_RESULT = {
    "wikidata_id": "Q794",
    "label": "Iran",
    "description": "sovereign state in Western Asia",
    "latitude": None,
    "longitude": None,
}

# Matches the real Wikibase REST API v0 search response shape:
# - top-level key is "results" (not "search")
# - label is nested in "display-label": {"value": ...}
# - description is nested in "description": {"value": ...}
IRAN_API_RESPONSE = {
    "results": [
        {
            "id": "Q794",
            "display-label": {"value": "Iran"},
            "description": {"value": "sovereign state in Western Asia"},
        }
    ]
}


def _make_resolver(mock_redis: MagicMock, mock_http: MagicMock) -> WikidataResolver:
    """Create a WikidataResolver with pre-injected mock clients."""
    resolver = WikidataResolver.__new__(WikidataResolver)
    resolver._redis = mock_redis
    resolver._http = mock_http
    resolver._static_token = None
    resolver._auth = None
    return resolver


# ---------------------------------------------------------------------------
# 1. Cache hit — Redis returns valid JSON
# ---------------------------------------------------------------------------


def test_resolve_cache_hit():
    """When Redis has a cached result, return it without calling the Wikidata API."""
    mock_redis = MagicMock()
    mock_http = MagicMock()

    # Redis returns the JSON-encoded result as bytes (as the real client does)
    mock_redis.get.return_value = json.dumps(IRAN_RESULT).encode()

    resolver = _make_resolver(mock_redis, mock_http)
    result = resolver.resolve("Iran")

    assert result == IRAN_RESULT
    mock_http.get.assert_not_called()
    mock_redis.get.assert_called_once_with("entity:iran:")


# ---------------------------------------------------------------------------
# 2. Cache miss + successful API call
# ---------------------------------------------------------------------------


def test_resolve_cache_miss_api_success():
    """On cache miss, call Wikidata, cache the result, and return it."""
    mock_redis = MagicMock()
    mock_http = MagicMock()

    # Redis returns None → cache miss
    mock_redis.get.return_value = None

    # httpx returns a successful response with one search result
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = IRAN_API_RESPONSE
    mock_response.raise_for_status.return_value = None
    mock_response.status_code = 200
    mock_http.get.return_value = mock_response

    resolver = _make_resolver(mock_redis, mock_http)

    with (
        patch("entity_resolver.resolver.time.sleep"),
        patch.object(resolver, "_is_wikimedia_internal", return_value=False),
    ):
        result = resolver.resolve("Iran")

    assert result == IRAN_RESULT

    # Verify the result was written to cache
    mock_redis.set.assert_called_once_with(
        "entity:iran:",
        json.dumps(IRAN_RESULT),
        ex=CACHE_TTL,
    )


# ---------------------------------------------------------------------------
# 3. Cache miss + API returns empty results
# ---------------------------------------------------------------------------


def test_resolve_cache_miss_api_no_results():
    """When Wikidata returns no search results, cache __NONE__ and return None."""
    mock_redis = MagicMock()
    mock_http = MagicMock()

    mock_redis.get.return_value = None

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {"results": []}
    mock_response.raise_for_status.return_value = None
    mock_response.status_code = 200
    mock_http.get.return_value = mock_response

    resolver = _make_resolver(mock_redis, mock_http)

    with patch("entity_resolver.resolver.time.sleep"):
        result = resolver.resolve("xyzzy_nonexistent_entity")

    assert result is None
    mock_redis.set.assert_called_once_with(
        "entity:xyzzy_nonexistent_entity:",
        CACHE_NONE_SENTINEL,
        ex=CACHE_TTL,
    )


# ---------------------------------------------------------------------------
# 4. Cache hit with __NONE__ sentinel
# ---------------------------------------------------------------------------


def test_resolve_cached_none_sentinel():
    """When Redis holds __NONE__, return None immediately without an API call."""
    mock_redis = MagicMock()
    mock_http = MagicMock()

    mock_redis.get.return_value = CACHE_NONE_SENTINEL.encode()

    resolver = _make_resolver(mock_redis, mock_http)
    result = resolver.resolve("xyzzy_nonexistent_entity")

    assert result is None
    mock_http.get.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Redis read error — fall through to API
# ---------------------------------------------------------------------------


def test_resolve_redis_read_error_falls_through():
    """If Redis.get() raises, treat it as a cache miss and still call Wikidata."""
    mock_redis = MagicMock()
    mock_http = MagicMock()

    mock_redis.get.side_effect = redis.RedisError("connection refused")

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = IRAN_API_RESPONSE
    mock_response.raise_for_status.return_value = None
    mock_response.status_code = 200
    mock_http.get.return_value = mock_response

    resolver = _make_resolver(mock_redis, mock_http)

    with (
        patch("entity_resolver.resolver.time.sleep"),
        patch.object(resolver, "_is_wikimedia_internal", return_value=False),
    ):
        result = resolver.resolve("Iran")

    assert result == IRAN_RESULT
    # The API was called despite the Redis error
    mock_http.get.assert_called_once()


# ---------------------------------------------------------------------------
# 6. Redis write error — result still returned to caller
# ---------------------------------------------------------------------------


def test_resolve_redis_write_error_continues():
    """If Redis.set() raises, the resolved result is still returned to the caller."""
    mock_redis = MagicMock()
    mock_http = MagicMock()

    mock_redis.get.return_value = None
    mock_redis.set.side_effect = redis.RedisError("out of memory")

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = IRAN_API_RESPONSE
    mock_response.raise_for_status.return_value = None
    mock_response.status_code = 200
    mock_http.get.return_value = mock_response

    resolver = _make_resolver(mock_redis, mock_http)

    with (
        patch("entity_resolver.resolver.time.sleep"),
        patch.object(resolver, "_is_wikimedia_internal", return_value=False),
    ):
        result = resolver.resolve("Iran")

    # The write failure is non-fatal — caller still gets the result
    assert result == IRAN_RESULT


# ---------------------------------------------------------------------------
# 7. HTTP error — cache __NONE__ and return None
# ---------------------------------------------------------------------------


def test_resolve_api_error_caches_none():
    """When httpx raises an HTTPError, cache __NONE__ and return None."""
    mock_redis = MagicMock()
    mock_http = MagicMock()

    mock_redis.get.return_value = None
    mock_http.get.side_effect = httpx.ConnectError("network unreachable")

    resolver = _make_resolver(mock_redis, mock_http)

    with patch("entity_resolver.resolver.time.sleep"):
        result = resolver.resolve("Iran")

    assert result is None
    mock_redis.set.assert_called_once_with(
        "entity:iran:",
        CACHE_NONE_SENTINEL,
        ex=CACHE_TTL,
    )
