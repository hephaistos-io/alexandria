"""Tests for Neo4jWriter — upsert logic and resource management."""

from unittest.mock import MagicMock, patch


@patch("relation_extractor.neo4j_writer.neo4j.GraphDatabase.driver")
class TestNeo4jWriter:
    def test_creates_constraint_on_init(self, mock_driver_ctor: MagicMock) -> None:
        """The uniqueness constraint is created at startup."""
        from relation_extractor.neo4j_writer import CONSTRAINT_QUERY, Neo4jWriter

        mock_driver = mock_driver_ctor.return_value
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_driver.session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        Neo4jWriter(uri="bolt://localhost:7687", auth=("neo4j", "test"))

        mock_session.run.assert_called_once_with(CONSTRAINT_QUERY)

    def test_upsert_relations_calls_execute_write_per_relation(
        self, mock_driver_ctor: MagicMock
    ) -> None:
        """Each relation gets its own execute_write call."""
        from relation_extractor.neo4j_writer import Neo4jWriter

        mock_driver = mock_driver_ctor.return_value
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_driver.session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        writer = Neo4jWriter(
            uri="bolt://localhost:7687", auth=("neo4j", "test")
        )

        relations = [
            {
                "source_qid": "Q1",
                "source_name": "Iran",
                "source_type": "GPE",
                "target_qid": "Q2",
                "target_name": "Syria",
                "target_type": "GPE",
                "relation_type": "ATTACKS",
                "confidence": 0.9,
            },
            {
                "source_qid": "Q3",
                "source_name": "USA",
                "source_type": "GPE",
                "target_qid": "Q1",
                "target_name": "Iran",
                "target_type": "GPE",
                "relation_type": "SANCTIONS",
                "confidence": 0.8,
            },
        ]

        writer.upsert_relations(relations, "https://example.com/article")

        assert mock_session.execute_write.call_count == 2

    def test_upsert_empty_list_is_noop(
        self, mock_driver_ctor: MagicMock
    ) -> None:
        """Upserting an empty relations list doesn't call execute_write."""
        from relation_extractor.neo4j_writer import Neo4jWriter

        mock_driver = mock_driver_ctor.return_value
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_driver.session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        writer = Neo4jWriter(
            uri="bolt://localhost:7687", auth=("neo4j", "test")
        )

        writer.upsert_relations([], "https://example.com/article")

        mock_session.execute_write.assert_not_called()

    def test_close_closes_driver(self, mock_driver_ctor: MagicMock) -> None:
        """close() delegates to the underlying driver."""
        from relation_extractor.neo4j_writer import Neo4jWriter

        mock_driver = mock_driver_ctor.return_value
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_driver.session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        writer = Neo4jWriter(
            uri="bolt://localhost:7687", auth=("neo4j", "test")
        )
        writer.close()

        mock_driver.close.assert_called_once()
