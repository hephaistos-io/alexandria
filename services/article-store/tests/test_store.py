from unittest.mock import MagicMock, patch

import pytest

from article_store.schema import (
    MIGRATE_ADD_AUTOMATIC_COLUMNS,
    MIGRATE_ADD_ENTITIES_COLUMN,
    MIGRATE_ADD_ENTITY_ROLE_COLUMNS,
    MIGRATE_RENAME_TO_MANUAL,
    MIGRATE_TOPIC_LABEL_TO_ARRAY,
    SCHEMA,
    SCHEMA_CLASSIFICATION_LABELS,
    SCHEMA_CONFLICT_EVENTS,
    SCHEMA_ENTITY_ROLE_TYPES,
    SCHEMA_EVENT_ARTICLES,
    SCHEMA_EVENT_CONFLICTS,
    SCHEMA_EVENTS,
    SCHEMA_INDEXES,
    SCHEMA_RELATION_TYPES,
    SEED_CLASSIFICATION_LABELS,
    SEED_ENTITY_ROLE_TYPES,
    SEED_RELATION_TYPES,
)
from article_store.store import ArticleStore

# A minimal article dict that mirrors what a ScrapedArticle JSON message looks like.
SAMPLE_ARTICLE = {
    "url": "https://example.com/article-1",
    "source": "example",
    "origin": "https://example.com",
    "title": "Example Article",
    "summary": "A brief summary.",
    "content": "Full article content here.",
    "published": "2024-01-15T10:00:00Z",   # note: "published", not "published_at"
    "fetched_at": "2024-01-15T11:00:00Z",
    "scraped_at": "2024-01-15T11:01:00Z",
}


@patch("article_store.store.psycopg.connect")
class TestArticleStore:
    def test_ensure_schema_executes_all_statements(
        self, mock_connect: MagicMock,
    ) -> None:
        """_ensure_schema should execute all schema + migration SQL and commit."""
        mock_conn = mock_connect.return_value
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        ArticleStore("postgresql://localhost/test")

        # apply_schema runs 17 statements: schema, 4 migrations, 2 table
        # creates, 3 seeds, relation_types table + seed, conflict_events
        # table, events table + 2 junction tables, indexes.
        assert mock_cursor.execute.call_count == 17
        mock_cursor.execute.assert_any_call(SCHEMA)
        mock_cursor.execute.assert_any_call(MIGRATE_TOPIC_LABEL_TO_ARRAY)
        mock_cursor.execute.assert_any_call(MIGRATE_RENAME_TO_MANUAL)
        mock_cursor.execute.assert_any_call(MIGRATE_ADD_AUTOMATIC_COLUMNS)
        mock_cursor.execute.assert_any_call(MIGRATE_ADD_ENTITIES_COLUMN)
        mock_cursor.execute.assert_any_call(SCHEMA_CLASSIFICATION_LABELS)
        mock_cursor.execute.assert_any_call(SEED_CLASSIFICATION_LABELS)
        mock_cursor.execute.assert_any_call(SCHEMA_ENTITY_ROLE_TYPES)
        mock_cursor.execute.assert_any_call(SEED_ENTITY_ROLE_TYPES)
        mock_cursor.execute.assert_any_call(MIGRATE_ADD_ENTITY_ROLE_COLUMNS)
        mock_cursor.execute.assert_any_call(SCHEMA_RELATION_TYPES)
        mock_cursor.execute.assert_any_call(SEED_RELATION_TYPES)
        mock_cursor.execute.assert_any_call(SCHEMA_CONFLICT_EVENTS)
        mock_cursor.execute.assert_any_call(SCHEMA_EVENTS)
        mock_cursor.execute.assert_any_call(SCHEMA_EVENT_ARTICLES)
        mock_cursor.execute.assert_any_call(SCHEMA_EVENT_CONFLICTS)
        mock_cursor.execute.assert_any_call(SCHEMA_INDEXES)
        mock_conn.commit.assert_called()

    def test_save_inserts_with_correct_params(self, mock_connect: MagicMock) -> None:
        """save() should execute INSERT with the correct column mapping."""
        mock_conn = mock_connect.return_value
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        store = ArticleStore("postgresql://localhost/test")
        # Reset call count after __init__ (which calls _ensure_schema).
        mock_cursor.execute.reset_mock()
        mock_conn.commit.reset_mock()

        store.save(SAMPLE_ARTICLE)

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        sql, params = call_args[0]

        assert "INSERT INTO articles" in sql
        assert "ON CONFLICT (url) DO NOTHING" in sql
        assert params == (
            "https://example.com/article-1",
            "example",
            "https://example.com",
            "Example Article",
            "A brief summary.",
            "Full article content here.",
            "2024-01-15T10:00:00Z",   # mapped from "published"
            "2024-01-15T11:00:00Z",
            "2024-01-15T11:01:00Z",
        )
        mock_conn.commit.assert_called_once()

    def test_save_returns_true_when_inserted(self, mock_connect: MagicMock) -> None:
        """save() returns True when a row was actually inserted (rowcount == 1)."""
        mock_conn = mock_connect.return_value
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        store = ArticleStore("postgresql://localhost/test")
        result = store.save(SAMPLE_ARTICLE)

        assert result is True

    def test_save_returns_false_when_duplicate(self, mock_connect: MagicMock) -> None:
        """save() returns False when DO NOTHING fires (rowcount == 0)."""
        mock_conn = mock_connect.return_value
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 0
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        store = ArticleStore("postgresql://localhost/test")
        result = store.save(SAMPLE_ARTICLE)

        assert result is False

    def test_save_maps_published_not_published_at(self, mock_connect: MagicMock) -> None:
        """save() reads 'published' from the dict, not 'published_at'."""
        mock_conn = mock_connect.return_value
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        article = dict(SAMPLE_ARTICLE)
        article["published"] = "2024-06-01T00:00:00Z"
        # Ensure there is no "published_at" key — the service must NOT look for it.
        article.pop("published_at", None)

        store = ArticleStore("postgresql://localhost/test")
        mock_cursor.execute.reset_mock()

        store.save(article)

        _, params = mock_cursor.execute.call_args[0]
        # published_at is the 7th positional param (index 6).
        assert params[6] == "2024-06-01T00:00:00Z"

    def test_save_allows_null_published(self, mock_connect: MagicMock) -> None:
        """save() passes None for published_at when the field is absent."""
        mock_conn = mock_connect.return_value
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        article = dict(SAMPLE_ARTICLE)
        article.pop("published", None)

        store = ArticleStore("postgresql://localhost/test")
        mock_cursor.execute.reset_mock()

        store.save(article)

        _, params = mock_cursor.execute.call_args[0]
        assert params[6] is None

    def test_save_raises_on_missing_required_field(
        self, mock_connect: MagicMock,
    ) -> None:
        """save() raises ValueError if a required field is missing."""
        mock_conn = mock_connect.return_value
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        store = ArticleStore("postgresql://localhost/test")

        article = dict(SAMPLE_ARTICLE)
        del article["title"]

        with pytest.raises(ValueError, match="title"):
            store.save(article)
