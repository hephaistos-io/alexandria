"""Tests for EventClient — get_event_detail.

Uses unittest.mock to patch psycopg.connect so no real database is needed.
The patch replaces the connection context manager and cursor with MagicMocks
whose return values we control.

Pattern: patch psycopg.connect as a context manager, then configure
fetchone/fetchall on the cursor mock to return whatever the test needs.
"""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from monitoring_api.event_client import EventClient, EventDetail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cursor(event_row, article_rows=None, conflict_rows=None):
    """Return a cursor mock pre-configured with the given query results.

    psycopg cursors are used as context managers inside EventClient, so the
    mock needs to support the `with conn.cursor() as cur:` pattern.
    fetchone() returns event_row; subsequent fetchall() calls return
    article_rows then conflict_rows in order.
    """
    cur = MagicMock()
    cur.fetchone.return_value = event_row
    cur.fetchall.side_effect = [article_rows or [], conflict_rows or []]

    # cursor is used as a context manager: `with conn.cursor() as cur`
    cur_cm = MagicMock()
    cur_cm.__enter__ = MagicMock(return_value=cur)
    cur_cm.__exit__ = MagicMock(return_value=False)
    return cur_cm


def _make_conn(cursor_cm):
    """Return a connection mock that yields cursor_cm from conn.cursor()."""
    conn = MagicMock()
    conn.cursor.return_value = cursor_cm

    conn_cm = MagicMock()
    conn_cm.__enter__ = MagicMock(return_value=conn)
    conn_cm.__exit__ = MagicMock(return_value=False)
    return conn_cm


def _make_client() -> EventClient:
    return EventClient(database_url="postgresql://fake/db")


# ---------------------------------------------------------------------------
# Fixtures — sample row data matching the SELECT column order
# ---------------------------------------------------------------------------

_SAMPLE_EVENT_ROW = (
    1,  # id
    "ukraine-conflict-2026",  # slug
    "Ukraine Conflict",  # title
    "active",  # status
    0.9123,  # heat
    ["Q212", "Q159"],  # entity_qids
    50.45,  # centroid_lat
    30.52,  # centroid_lng
    datetime(2026, 1, 1, tzinfo=timezone.utc),  # first_seen
    datetime(2026, 3, 20, tzinfo=timezone.utc),  # last_seen
    2,  # article_count
    1,  # conflict_count
)

_SAMPLE_ARTICLE_ROWS = [
    (
        10,  # id
        "Kyiv under attack",  # title
        "bbc",  # source
        "https://bbc.com/news/10",  # url
        "A brief summary.",  # summary
        datetime(2026, 3, 18, tzinfo=timezone.utc),  # published_at
        ["CONFLICT"],  # automatic_labels
        [{"text": "Ukraine", "wikidata_id": "Q212"}],  # entities (already list)
    ),
    (
        11,
        "Sanctions tightened",
        "reuters",
        "https://reuters.com/11",
        None,
        None,
        None,
        None,
    ),
]

_SAMPLE_CONFLICT_ROWS = [
    (
        5,  # id
        "Shelling in Kharkiv",  # title
        49.99,  # latitude
        36.23,  # longitude
        date(2026, 3, 17),  # event_date
        "Kharkiv, Ukraine",  # place_desc
        "acled",  # source
    ),
]


# ---------------------------------------------------------------------------
# Tests — get_event_detail returns None when event not found
# ---------------------------------------------------------------------------


def test_get_event_detail_returns_none_when_event_missing():
    """fetchone returns None → get_event_detail returns None."""
    cur_cm = _make_cursor(event_row=None)
    conn_cm = _make_conn(cur_cm)

    client = _make_client()
    with patch("psycopg.connect", return_value=conn_cm):
        result = client.get_event_detail(99)

    assert result is None


# ---------------------------------------------------------------------------
# Tests — get_event_detail returns EventDetail when event found
# ---------------------------------------------------------------------------


def test_get_event_detail_returns_event_detail():
    """Happy path: all three queries return data; result is a fully-populated EventDetail."""
    cur_cm = _make_cursor(
        event_row=_SAMPLE_EVENT_ROW,
        article_rows=_SAMPLE_ARTICLE_ROWS,
        conflict_rows=_SAMPLE_CONFLICT_ROWS,
    )
    conn_cm = _make_conn(cur_cm)

    client = _make_client()
    with patch("psycopg.connect", return_value=conn_cm):
        result = client.get_event_detail(1)

    assert isinstance(result, EventDetail)
    assert result.id == 1
    assert result.slug == "ukraine-conflict-2026"
    assert result.title == "Ukraine Conflict"
    assert result.status == "active"
    assert result.heat == round(0.9123, 4)
    assert result.entity_qids == ["Q212", "Q159"]
    assert result.centroid_lat == 50.45
    assert result.centroid_lng == 30.52
    assert result.first_seen == "2026-01-01T00:00:00+00:00"
    assert result.last_seen == "2026-03-20T00:00:00+00:00"
    assert result.article_count == 2
    assert result.conflict_count == 1


def test_get_event_detail_articles_are_mapped_correctly():
    """Articles list is populated with correct field values."""
    cur_cm = _make_cursor(
        event_row=_SAMPLE_EVENT_ROW,
        article_rows=_SAMPLE_ARTICLE_ROWS,
        conflict_rows=[],
    )
    conn_cm = _make_conn(cur_cm)

    client = _make_client()
    with patch("psycopg.connect", return_value=conn_cm):
        result = client.get_event_detail(1)

    assert result is not None
    assert len(result.articles) == 2

    first = result.articles[0]
    assert first.id == 10
    assert first.title == "Kyiv under attack"
    assert first.source == "bbc"
    assert first.url == "https://bbc.com/news/10"
    assert first.summary == "A brief summary."
    assert first.published_at == "2026-03-18T00:00:00+00:00"
    assert first.automatic_labels == ["CONFLICT"]
    assert first.entities == [{"text": "Ukraine", "wikidata_id": "Q212"}]

    second = result.articles[1]
    assert second.summary is None
    assert second.published_at is None
    assert second.automatic_labels is None
    assert second.entities is None


def test_get_event_detail_conflicts_are_mapped_correctly():
    """Conflicts list is populated with correct field values."""
    cur_cm = _make_cursor(
        event_row=_SAMPLE_EVENT_ROW,
        article_rows=[],
        conflict_rows=_SAMPLE_CONFLICT_ROWS,
    )
    conn_cm = _make_conn(cur_cm)

    client = _make_client()
    with patch("psycopg.connect", return_value=conn_cm):
        result = client.get_event_detail(1)

    assert result is not None
    assert len(result.conflicts) == 1

    c = result.conflicts[0]
    assert c.id == 5
    assert c.title == "Shelling in Kharkiv"
    assert c.latitude == 49.99
    assert c.longitude == 36.23
    assert c.event_date == "2026-03-17"
    assert c.place_desc == "Kharkiv, Ukraine"
    assert c.source == "acled"


def test_get_event_detail_no_articles_or_conflicts():
    """Event with no linked articles or conflicts returns empty lists."""
    cur_cm = _make_cursor(
        event_row=_SAMPLE_EVENT_ROW,
        article_rows=[],
        conflict_rows=[],
    )
    conn_cm = _make_conn(cur_cm)

    client = _make_client()
    with patch("psycopg.connect", return_value=conn_cm):
        result = client.get_event_detail(1)

    assert result is not None
    assert result.articles == []
    assert result.conflicts == []


def test_get_event_detail_entities_parsed_from_json_string():
    """entities stored as a JSON string (TEXT column) are parsed into a list."""
    import json

    article_row_with_json_string = (
        12,
        "Test article",
        "source",
        "https://example.com",
        None,
        None,
        None,
        json.dumps([{"text": "Russia", "wikidata_id": "Q159"}]),  # string, not list
    )

    cur_cm = _make_cursor(
        event_row=_SAMPLE_EVENT_ROW,
        article_rows=[article_row_with_json_string],
        conflict_rows=[],
    )
    conn_cm = _make_conn(cur_cm)

    client = _make_client()
    with patch("psycopg.connect", return_value=conn_cm):
        result = client.get_event_detail(1)

    assert result is not None
    assert result.articles[0].entities == [{"text": "Russia", "wikidata_id": "Q159"}]


def test_get_event_detail_null_centroid():
    """Events without a centroid have None for lat/lng."""
    event_row_no_centroid = list(_SAMPLE_EVENT_ROW)
    event_row_no_centroid[6] = None  # centroid_lat
    event_row_no_centroid[7] = None  # centroid_lng

    cur_cm = _make_cursor(
        event_row=tuple(event_row_no_centroid),
        article_rows=[],
        conflict_rows=[],
    )
    conn_cm = _make_conn(cur_cm)

    client = _make_client()
    with patch("psycopg.connect", return_value=conn_cm):
        result = client.get_event_detail(1)

    assert result is not None
    assert result.centroid_lat is None
    assert result.centroid_lng is None
