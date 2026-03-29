"""Tests for database query functions.

These test the query functions' data mapping logic using mocked psycopg
connections, not actual database calls.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

from event_detector.models import DetectedEvent
from event_detector.queries import (
    decay_historical_events,
    fetch_existing_events,
    fetch_recent_articles,
    fetch_recent_conflicts,
    link_articles,
    link_conflicts,
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
        conn = _mock_conn([(1, 31.5, 34.5, now, "Israel")])
        results = fetch_recent_conflicts(conn)
        assert len(results) == 1
        assert results[0].latitude == 31.5
        assert results[0].country == "Israel"


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
        # upsert_event no longer commits — caller handles the transaction.
        conn.commit.assert_not_called()

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

    def test_upsert_does_not_commit(self) -> None:
        """upsert_event should NOT commit — caller handles the transaction."""
        now = datetime.now(timezone.utc)
        event = DetectedEvent(
            slug="test",
            title="Test",
            status="emerging",
            heat=1.0,
            entity_qids=[],
            centroid_lat=None,
            centroid_lng=None,
            first_seen=now,
            last_seen=now,
        )
        conn = _mock_conn([])
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (1,)
        upsert_event(conn, event)
        conn.commit.assert_not_called()


class TestLinkArticles:
    def test_deletes_then_inserts(self) -> None:
        conn = _mock_conn([])
        cursor = conn.cursor.return_value.__enter__.return_value
        link_articles(conn, event_id=1, article_ids=[10, 20, 30])
        # First call is DELETE, then executemany for inserts.
        assert cursor.execute.call_count == 1  # DELETE
        assert cursor.executemany.call_count == 1
        params = cursor.executemany.call_args[0][1]
        assert len(params) == 3

    def test_empty_article_ids_only_deletes(self) -> None:
        conn = _mock_conn([])
        cursor = conn.cursor.return_value.__enter__.return_value
        link_articles(conn, event_id=1, article_ids=[])
        assert cursor.execute.call_count == 1  # DELETE only
        assert cursor.executemany.call_count == 0

    def test_does_not_commit(self) -> None:
        conn = _mock_conn([])
        link_articles(conn, event_id=1, article_ids=[10])
        conn.commit.assert_not_called()


class TestLinkConflicts:
    def test_deletes_then_inserts(self) -> None:
        conn = _mock_conn([])
        cursor = conn.cursor.return_value.__enter__.return_value
        link_conflicts(conn, event_id=1, conflict_ids=[5, 6])
        assert cursor.execute.call_count == 1  # DELETE
        assert cursor.executemany.call_count == 1

    def test_empty_ids_only_deletes(self) -> None:
        conn = _mock_conn([])
        cursor = conn.cursor.return_value.__enter__.return_value
        link_conflicts(conn, event_id=1, conflict_ids=[])
        assert cursor.execute.call_count == 1
        assert cursor.executemany.call_count == 0

    def test_does_not_commit(self) -> None:
        conn = _mock_conn([])
        link_conflicts(conn, event_id=1, conflict_ids=[5])
        conn.commit.assert_not_called()


class TestDecayHistoricalEvents:
    def test_returns_decayed_count(self) -> None:
        conn = _mock_conn([])
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.rowcount = 3
        result = decay_historical_events(conn, heat_threshold=0.5)
        assert result == 3
        conn.commit.assert_called()

    def test_excludes_matched_ids(self) -> None:
        conn = _mock_conn([])
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.rowcount = 1
        decay_historical_events(conn, heat_threshold=0.5, exclude_ids={7, 8})
        # Should use the query branch with ALL(%s) exclusion.
        sql = cursor.execute.call_args[0][0]
        assert "ALL" in sql

    def test_no_exclusion_when_empty(self) -> None:
        conn = _mock_conn([])
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.rowcount = 0
        decay_historical_events(conn, heat_threshold=0.5, exclude_ids=set())
        sql = cursor.execute.call_args[0][0]
        assert "ALL" not in sql
