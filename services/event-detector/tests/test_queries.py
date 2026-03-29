"""Tests for database query functions.

These test the query functions' data mapping logic using mocked psycopg
connections, not actual database calls.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

from event_detector.models import DetectedEvent
from event_detector.queries import (
    fetch_existing_events,
    fetch_recent_articles,
    fetch_recent_conflicts,
    upsert_event,
)


def _mock_conn(rows: list[tuple]) -> MagicMock:
    """Create a mock psycopg connection that returns the given rows."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    cursor.fetchall.return_value = rows
    cursor.fetchone.return_value = (1,)
    return conn


class TestFetchRecentArticles:
    def test_maps_rows_to_article_rows(self) -> None:
        entities = [{"wikidata_id": "Q1", "text": "Test"}]
        now = datetime.now(timezone.utc)
        conn = _mock_conn(
            [
                (1, "Title", entities, ["CONFLICT"], now),
            ]
        )
        results = fetch_recent_articles(conn, days=14)
        assert len(results) == 1
        assert results[0].id == 1
        assert results[0].title == "Title"
        assert results[0].entities == entities
        assert results[0].automatic_labels == ["CONFLICT"]

    def test_handles_string_entities(self) -> None:
        """If entities come back as a JSON string, they should be parsed."""
        entities_str = json.dumps([{"wikidata_id": "Q1"}])
        conn = _mock_conn([(1, "T", entities_str, None, None)])
        results = fetch_recent_articles(conn)
        assert results[0].entities == [{"wikidata_id": "Q1"}]

    def test_empty_result(self) -> None:
        conn = _mock_conn([])
        assert fetch_recent_articles(conn) == []


class TestFetchRecentConflicts:
    def test_maps_rows(self) -> None:
        now = datetime.now(timezone.utc)
        conn = _mock_conn([(1, 31.5, 34.5, now)])
        results = fetch_recent_conflicts(conn)
        assert len(results) == 1
        assert results[0].latitude == 31.5


class TestFetchExistingEvents:
    def test_maps_rows(self) -> None:
        now = datetime.now(timezone.utc)
        conn = _mock_conn(
            [
                (1, "test-slug", "Test", "active", 5.0, ["Q1"], 31.0, 34.0, now, now),
            ]
        )
        results = fetch_existing_events(conn)
        assert len(results) == 1
        assert results[0].slug == "test-slug"
        assert results[0].entity_qids == ["Q1"]


class TestUpsertEvent:
    def test_insert_new_event(self) -> None:
        now = datetime.now(timezone.utc)
        event = DetectedEvent(
            slug="test",
            title="Test",
            status="emerging",
            heat=3.0,
            entity_qids=["Q1"],
            centroid_lat=31.0,
            centroid_lng=34.0,
            first_seen=now,
            last_seen=now,
        )
        conn = _mock_conn([])
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (42,)
        result = upsert_event(conn, event)
        assert result == 42
        conn.commit.assert_called()

    def test_update_existing_event(self) -> None:
        now = datetime.now(timezone.utc)
        event = DetectedEvent(
            slug="test",
            title="Test",
            status="active",
            heat=6.0,
            entity_qids=["Q1"],
            centroid_lat=31.0,
            centroid_lng=34.0,
            first_seen=now,
            last_seen=now,
            existing_id=7,
        )
        conn = _mock_conn([])
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (7,)
        result = upsert_event(conn, event)
        assert result == 7
