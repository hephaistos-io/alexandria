"""Tests for handle_message in __main__.py — the integration glue."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from ner_tagger.__main__ import handle_message
from ner_tagger.models import TaggedMention


def _base_payload() -> dict:
    return {
        "url": "https://example.com/article",
        "source": "rss",
        "origin": "bbc_world",
        "title": "Test Article",
        "summary": "A summary.",
        "content": "Iran announced new sanctions.",
        "fetched_at": "2026-03-20T14:30:00+00:00",
        "scraped_at": "2026-03-20T14:31:00+00:00",
    }


def test_valid_payload_publishes():
    """A complete payload is tagged and published."""
    tagger = MagicMock()
    tagger.tag.return_value = [
        TaggedMention(text="Iran", label="GPE", start_char=0, end_char=4),
    ]
    publisher = MagicMock()

    handle_message(_base_payload(), tagger, publisher)

    publisher.publish.assert_called_once()
    article = publisher.publish.call_args[0][0]
    assert article.url == "https://example.com/article"
    assert len(article.entities) == 1
    assert article.entities[0]["text"] == "Iran"
    assert article.entities[0]["label"] == "GPE"


def test_missing_url_skips():
    """A payload without 'url' is skipped — no publish."""
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
    """A payload missing a required field (e.g. 'title') is skipped."""
    payload = _base_payload()
    del payload["title"]
    publisher = MagicMock()

    handle_message(payload, MagicMock(), publisher)

    publisher.publish.assert_not_called()


def test_no_entities_still_publishes():
    """An article with no NER entities is still published."""
    tagger = MagicMock()
    tagger.tag.return_value = []
    publisher = MagicMock()

    handle_message(_base_payload(), tagger, publisher)

    publisher.publish.assert_called_once()
    article = publisher.publish.call_args[0][0]
    assert article.entities == []


def test_tagged_at_is_iso_timestamp():
    """The tagged_at field is a valid ISO 8601 timestamp."""
    tagger = MagicMock()
    tagger.tag.return_value = []
    publisher = MagicMock()

    handle_message(_base_payload(), tagger, publisher)

    article = publisher.publish.call_args[0][0]
    # Should parse without error
    dt = datetime.fromisoformat(article.tagged_at)
    assert dt.tzinfo == timezone.utc


def test_optional_published_field():
    """The optional 'published' field is passed through when present."""
    tagger = MagicMock()
    tagger.tag.return_value = []
    publisher = MagicMock()
    payload = _base_payload()
    payload["published"] = "2026-03-20T12:00:00+00:00"

    handle_message(payload, tagger, publisher)

    article = publisher.publish.call_args[0][0]
    assert article.published == "2026-03-20T12:00:00+00:00"


def test_missing_published_defaults_to_none():
    """When 'published' is absent, it defaults to None."""
    tagger = MagicMock()
    tagger.tag.return_value = []
    publisher = MagicMock()
    payload = _base_payload()
    # 'published' is not in _base_payload — confirm it's absent
    assert "published" not in payload

    handle_message(payload, tagger, publisher)

    article = publisher.publish.call_args[0][0]
    assert article.published is None


def test_content_defaults_to_empty_string():
    """When 'content' is absent, it defaults to an empty string."""
    tagger = MagicMock()
    tagger.tag.return_value = []
    publisher = MagicMock()
    payload = _base_payload()
    del payload["content"]

    handle_message(payload, tagger, publisher)

    tagger.tag.assert_called_once_with("")
    article = publisher.publish.call_args[0][0]
    assert article.content == ""


@patch("ner_tagger.__main__.logger")
def test_missing_multiple_fields_logs_all(mock_logger: MagicMock):
    """When multiple fields are missing, the error log names all of them."""
    payload = {"url": "https://example.com/x"}
    publisher = MagicMock()

    handle_message(payload, MagicMock(), publisher)

    publisher.publish.assert_not_called()
    # The error call should list the missing fields
    log_args = mock_logger.error.call_args[0]
    assert "source" in str(log_args)
    assert "title" in str(log_args)
