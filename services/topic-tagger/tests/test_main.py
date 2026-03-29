"""Tests for handle_message in __main__.py — payload validation and pipeline."""

from unittest.mock import MagicMock, patch

from topic_tagger.__main__ import handle_message


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
                "auto_role": "ACTOR",
                "auto_role_confidence": 0.85,
            },
        ],
    }


def test_valid_payload_classifies_and_publishes():
    """A complete payload with entity roles is classified and published."""
    classifier = MagicMock()
    classifier.classify.return_value = [
        {"name": "CONFLICT", "score": 0.85},
    ]
    publisher = MagicMock()

    handle_message(_base_payload(), classifier, publisher)

    classifier.classify.assert_called_once()
    publisher.publish.assert_called_once()


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


def test_empty_entities_no_labels_does_not_publish():
    """Empty entities + no labels → nothing to publish."""
    classifier = MagicMock()
    classifier.classify.return_value = []
    publisher = MagicMock()
    payload = _base_payload()
    payload["entities"] = []

    handle_message(payload, classifier, publisher)

    publisher.publish.assert_not_called()


def test_empty_entities_with_labels_publishes():
    """Empty entities but topic labels → still publishes."""
    classifier = MagicMock()
    classifier.classify.return_value = [{"name": "CONFLICT", "score": 0.9}]
    publisher = MagicMock()
    payload = _base_payload()
    payload["entities"] = []

    handle_message(payload, classifier, publisher)

    publisher.publish.assert_called_once()


def test_empty_text_skips():
    """A payload with empty title/content/summary is skipped."""
    classifier = MagicMock()
    publisher = MagicMock()
    payload = _base_payload()
    payload["title"] = ""
    payload["content"] = ""

    handle_message(payload, classifier, publisher)

    classifier.classify.assert_not_called()
    publisher.publish.assert_not_called()


@patch("topic_tagger.__main__.logger")
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
