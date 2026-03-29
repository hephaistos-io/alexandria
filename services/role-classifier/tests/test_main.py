"""Tests for handle_message in __main__.py — payload validation and pipeline."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from role_classifier.__main__ import handle_message


def _base_payload() -> dict:
    return {
        "url": "https://example.com/article",
        "title": "Iran imposes sanctions",
        "content": "Iran moved forces to the border.",
        "entities": [
            {
                "text": "Iran",
                "label": "GPE",
                "start": 0,
                "end": 4,
                "canonical_name": "Iran",
                "wikidata_id": "Q794",
            },
        ],
    }


def test_valid_payload_classifies_and_publishes():
    """A complete payload is classified and published."""
    classifier = MagicMock()
    classifier.classify_entity_roles.return_value = [
        {
            "text": "Iran",
            "label": "GPE",
            "start": 0,
            "end": 4,
            "auto_role": "ACTOR",
            "auto_role_confidence": 0.85,
        }
    ]
    publisher = MagicMock()

    handle_message(_base_payload(), classifier, publisher)

    classifier.classify_entity_roles.assert_called_once()
    publisher.publish.assert_called_once()
    published = publisher.publish.call_args[0][0]
    assert "role_classified_at" in published
    assert published["entities"][0]["auto_role"] == "ACTOR"


def test_missing_url_skips():
    """A payload without 'url' is skipped."""
    payload = _base_payload()
    del payload["url"]
    publisher = MagicMock()

    handle_message(payload, MagicMock(), publisher)

    publisher.publish.assert_not_called()


def test_empty_url_skips():
    """A payload with an empty 'url' is skipped."""
    payload = _base_payload()
    payload["url"] = ""
    publisher = MagicMock()

    handle_message(payload, MagicMock(), publisher)

    publisher.publish.assert_not_called()


def test_missing_required_field_skips():
    """A payload missing a required field (e.g. 'entities') is skipped."""
    payload = _base_payload()
    del payload["entities"]
    publisher = MagicMock()

    handle_message(payload, MagicMock(), publisher)

    publisher.publish.assert_not_called()


def test_entities_not_a_list_skips():
    """If 'entities' is not a list, the message is skipped."""
    payload = _base_payload()
    payload["entities"] = "not-a-list"
    publisher = MagicMock()

    handle_message(payload, MagicMock(), publisher)

    publisher.publish.assert_not_called()


def test_empty_entities_still_publishes():
    """Empty entities list is valid — message still gets published."""
    classifier = MagicMock()
    classifier.classify_entity_roles.return_value = []
    publisher = MagicMock()
    payload = _base_payload()
    payload["entities"] = []

    handle_message(payload, classifier, publisher)

    publisher.publish.assert_called_once()


def test_role_classified_at_is_iso_timestamp():
    """The role_classified_at field is a valid ISO 8601 timestamp."""
    classifier = MagicMock()
    classifier.classify_entity_roles.return_value = []
    publisher = MagicMock()

    handle_message(_base_payload(), classifier, publisher)

    published = publisher.publish.call_args[0][0]
    dt = datetime.fromisoformat(published["role_classified_at"])
    assert dt.tzinfo == timezone.utc


@patch("role_classifier.__main__.logger")
def test_missing_multiple_fields_logs_all(mock_logger: MagicMock):
    """When multiple fields are missing, the error log names all of them."""
    payload = {"url": "https://example.com/x"}
    publisher = MagicMock()

    handle_message(payload, MagicMock(), publisher)

    publisher.publish.assert_not_called()
    log_args = mock_logger.error.call_args[0]
    assert "title" in str(log_args)
    assert "content" in str(log_args)
    assert "entities" in str(log_args)
