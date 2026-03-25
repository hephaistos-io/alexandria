"""Tests for handle_message and _parse_neo4j_auth in __main__.py."""

from unittest.mock import MagicMock, patch

import pytest

from relation_extractor.__main__ import _parse_neo4j_auth, handle_message

# ---------------------------------------------------------------------------
# _parse_neo4j_auth
# ---------------------------------------------------------------------------


class TestParseNeo4jAuth:
    def test_basic_user_password(self) -> None:
        assert _parse_neo4j_auth("neo4j/alexandria") == (
            "neo4j",
            "alexandria",
        )

    def test_password_with_slash(self) -> None:
        """Passwords containing slashes are supported (split on first only)."""
        assert _parse_neo4j_auth("neo4j/pass/with/slashes") == (
            "neo4j",
            "pass/with/slashes",
        )

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="user/password"):
            _parse_neo4j_auth("")

    def test_no_slash_raises(self) -> None:
        with pytest.raises(ValueError, match="user/password"):
            _parse_neo4j_auth("neo4j_no_slash")


# ---------------------------------------------------------------------------
# handle_message
# ---------------------------------------------------------------------------


def _base_payload() -> dict:
    return {
        "url": "https://example.com/article",
        "title": "Test Article",
        "content": "Iran attacks Syria in new offensive.",
        "entities": [
            {
                "wikidata_id": "Q794",
                "canonical_name": "Iran",
                "text": "Iran",
                "label": "GPE",
                "start": 0,
                "end": 4,
            },
            {
                "wikidata_id": "Q858",
                "canonical_name": "Syria",
                "text": "Syria",
                "label": "GPE",
                "start": 13,
                "end": 18,
            },
        ],
    }


def test_valid_payload_calls_extractor_and_writer():
    """A complete payload is processed and relations are written."""
    extractor = MagicMock()
    extractor.extract_relations.return_value = [
        {
            "source_qid": "Q794",
            "source_name": "Iran",
            "source_type": "GPE",
            "target_qid": "Q858",
            "target_name": "Syria",
            "target_type": "GPE",
            "relation_type": "ATTACKS",
            "confidence": 0.9,
        }
    ]
    writer = MagicMock()

    handle_message(_base_payload(), extractor, writer)

    extractor.extract_relations.assert_called_once()
    writer.upsert_relations.assert_called_once()


def test_missing_url_skips():
    """A payload without 'url' is skipped."""
    payload = _base_payload()
    del payload["url"]
    extractor = MagicMock()
    writer = MagicMock()

    handle_message(payload, extractor, writer)

    extractor.extract_relations.assert_not_called()


def test_empty_url_skips():
    """A payload with an empty 'url' is skipped."""
    payload = _base_payload()
    payload["url"] = ""
    extractor = MagicMock()
    writer = MagicMock()

    handle_message(payload, extractor, writer)

    extractor.extract_relations.assert_not_called()


def test_missing_required_field_skips():
    """A payload missing a required field (e.g. 'entities') is skipped."""
    payload = _base_payload()
    del payload["entities"]
    extractor = MagicMock()
    writer = MagicMock()

    handle_message(payload, extractor, writer)

    extractor.extract_relations.assert_not_called()


def test_entities_not_a_list_skips():
    """If 'entities' is not a list, the message is skipped."""
    payload = _base_payload()
    payload["entities"] = "not-a-list"
    extractor = MagicMock()
    writer = MagicMock()

    handle_message(payload, extractor, writer)

    extractor.extract_relations.assert_not_called()


def test_empty_entities_skips():
    """An article with no entities is skipped."""
    payload = _base_payload()
    payload["entities"] = []
    extractor = MagicMock()
    writer = MagicMock()

    handle_message(payload, extractor, writer)

    extractor.extract_relations.assert_not_called()


def test_empty_content_skips():
    """An article with empty content is skipped."""
    payload = _base_payload()
    payload["content"] = ""
    extractor = MagicMock()
    writer = MagicMock()

    handle_message(payload, extractor, writer)

    extractor.extract_relations.assert_not_called()


def test_no_relations_extracted_skips_writer():
    """When no relations are found, writer is not called."""
    extractor = MagicMock()
    extractor.extract_relations.return_value = []
    writer = MagicMock()

    handle_message(_base_payload(), extractor, writer)

    extractor.extract_relations.assert_called_once()
    writer.upsert_relations.assert_not_called()


@patch("relation_extractor.__main__.logger")
def test_missing_multiple_fields_logs_all(mock_logger: MagicMock):
    """When multiple fields are missing, the error log names all of them."""
    payload = {"url": "https://example.com/x"}
    extractor = MagicMock()
    writer = MagicMock()

    handle_message(payload, extractor, writer)

    extractor.extract_relations.assert_not_called()
    log_args = mock_logger.error.call_args[0]
    assert "title" in str(log_args)
    assert "content" in str(log_args)
    assert "entities" in str(log_args)
