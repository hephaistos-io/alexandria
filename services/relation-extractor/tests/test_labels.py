"""Tests for the labels module — loading relation types from the database."""

from unittest.mock import MagicMock, patch

from relation_extractor.labels import RelationDefinition, load_relation_types


@patch("relation_extractor.labels.psycopg.connect")
class TestLoadRelationTypes:
    def test_returns_relation_definitions(self, mock_connect: MagicMock) -> None:
        """Happy path: rows are converted to RelationDefinition objects."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            ("SANCTIONS", "imposes sanctions against", True),
            ("ALLIED_WITH", "is allied with", False),
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

        result = load_relation_types("postgresql://localhost/test")

        assert len(result) == 2
        assert isinstance(result[0], RelationDefinition)
        assert result[0].name == "SANCTIONS"
        assert result[0].description == "imposes sanctions against"
        assert result[0].directed is True
        assert result[1].name == "ALLIED_WITH"
        assert result[1].directed is False

    def test_returns_empty_on_db_error(self, mock_connect: MagicMock) -> None:
        """Returns empty list when the database is unreachable."""
        mock_connect.side_effect = Exception("connection refused")

        result = load_relation_types("postgresql://localhost/test")

        assert result == []

    def test_returns_empty_when_no_rows(self, mock_connect: MagicMock) -> None:
        """Returns empty list when no enabled relation types exist."""
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

        result = load_relation_types("postgresql://localhost/test")

        assert result == []
