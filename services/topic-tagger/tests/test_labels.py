"""Tests for the labels module — loading classification labels from the database."""

from unittest.mock import MagicMock, patch

from topic_tagger.labels import LabelDefinition, load_labels


@patch("topic_tagger.labels.psycopg.connect")
class TestLoadLabels:
    def test_returns_label_definitions(
        self, mock_connect: MagicMock
    ) -> None:
        """Happy path: rows are converted to LabelDefinition objects."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            ("CONFLICT", "armed conflicts, wars, and military operations"),
            ("POLITICS", "political events and governance"),
        ]
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(
            return_value=mock_cur
        )
        mock_conn.cursor.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_connect.return_value = mock_conn

        result = load_labels("postgresql://localhost/test")

        assert len(result) == 2
        assert isinstance(result[0], LabelDefinition)
        assert result[0].name == "CONFLICT"
        assert result[0].description == "armed conflicts, wars, and military operations"
        assert result[1].name == "POLITICS"

    def test_returns_empty_on_db_error(
        self, mock_connect: MagicMock
    ) -> None:
        """Returns empty list when the database is unreachable."""
        mock_connect.side_effect = Exception("connection refused")

        result = load_labels("postgresql://localhost/test")

        assert result == []

    def test_returns_empty_when_no_rows(
        self, mock_connect: MagicMock
    ) -> None:
        """Returns empty list when no enabled labels exist."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(
            return_value=mock_cur
        )
        mock_conn.cursor.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_connect.return_value = mock_conn

        result = load_labels("postgresql://localhost/test")

        assert result == []
