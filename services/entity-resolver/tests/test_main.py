"""Tests for entity_resolver.__main__ — message handling and validation."""

from unittest.mock import MagicMock, patch

from entity_resolver.__main__ import handle_message
from entity_resolver.resolver import RateLimitedError

# A minimal payload matching what the NER tagger sends downstream.
SAMPLE_PAYLOAD = {
    "url": "https://example.com/article-1",
    "source": "example",
    "origin": "https://example.com",
    "title": "Example Article",
    "summary": "A brief summary.",
    "content": "Full article content here.",
    "fetched_at": "2024-01-15T11:00:00Z",
    "scraped_at": "2024-01-15T11:01:00Z",
    "tagged_at": "2024-01-15T11:02:00Z",
    "entities": [
        {"text": "Iran", "label": "GPE"},
    ],
}


class TestHandleMessage:
    def test_valid_payload_publishes(self) -> None:
        """A complete payload should resolve entities and publish."""
        resolver = MagicMock()
        resolver.resolve.return_value = {
            "wikidata_id": "Q794",
            "label": "Iran",
            "description": "country",
            "latitude": None,
            "longitude": None,
        }
        publisher = MagicMock()

        handle_message(dict(SAMPLE_PAYLOAD), resolver, publisher)

        resolver.resolve.assert_called_once_with("Iran", label="GPE")
        publisher.publish.assert_called_once()

    def test_missing_url_skips(self) -> None:
        """Messages without 'url' should be logged and skipped."""
        resolver = MagicMock()
        publisher = MagicMock()
        payload = dict(SAMPLE_PAYLOAD)
        del payload["url"]

        handle_message(payload, resolver, publisher)

        resolver.resolve.assert_not_called()
        publisher.publish.assert_not_called()

    def test_empty_url_skips(self) -> None:
        """Messages with empty 'url' should be logged and skipped."""
        resolver = MagicMock()
        publisher = MagicMock()
        payload = dict(SAMPLE_PAYLOAD)
        payload["url"] = ""

        handle_message(payload, resolver, publisher)

        resolver.resolve.assert_not_called()
        publisher.publish.assert_not_called()

    def test_missing_required_field_skips(self) -> None:
        """Messages missing a required field (other than url) should be skipped."""
        resolver = MagicMock()
        publisher = MagicMock()
        payload = dict(SAMPLE_PAYLOAD)
        del payload["title"]

        handle_message(payload, resolver, publisher)

        resolver.resolve.assert_not_called()
        publisher.publish.assert_not_called()

    def test_malformed_entity_entry_handled(self) -> None:
        """A non-dict entity entry should be skipped but not crash the message."""
        resolver = MagicMock()
        resolver.resolve.return_value = None
        publisher = MagicMock()
        payload = dict(SAMPLE_PAYLOAD)
        payload["entities"] = [
            "not-a-dict",
            {"text": "Iran", "label": "GPE"},
        ]

        handle_message(payload, resolver, publisher)

        # Only the valid entity should be resolved
        resolver.resolve.assert_called_once_with("Iran", label="GPE")
        publisher.publish.assert_called_once()

    def test_entity_missing_text_handled(self) -> None:
        """An entity dict without 'text' should be skipped."""
        resolver = MagicMock()
        resolver.resolve.return_value = None
        publisher = MagicMock()
        payload = dict(SAMPLE_PAYLOAD)
        payload["entities"] = [{"label": "GPE"}]  # missing "text"

        handle_message(payload, resolver, publisher)

        resolver.resolve.assert_not_called()
        publisher.publish.assert_called_once()

    def test_rate_limited_requeues(self) -> None:
        """When rate-limited, the message should be re-enqueued with incremented retry count."""
        resolver = MagicMock()
        resolver.resolve.side_effect = RateLimitedError("Iran")
        publisher = MagicMock()
        payload = dict(SAMPLE_PAYLOAD)

        handle_message(payload, resolver, publisher)

        publisher.requeue.assert_called_once()
        publisher.publish.assert_not_called()
        assert payload["_resolve_retries"] == 1

    def test_max_retries_publishes_partial(self) -> None:
        """After MAX_RESOLVE_RETRIES, publish with partially-resolved entities."""
        resolver = MagicMock()
        resolver.resolve.side_effect = RateLimitedError("Iran")
        publisher = MagicMock()
        payload = dict(SAMPLE_PAYLOAD)
        payload["_resolve_retries"] = 3  # already at max

        handle_message(payload, resolver, publisher)

        publisher.publish.assert_called_once()
        publisher.requeue.assert_not_called()

    def test_no_entities_still_publishes(self) -> None:
        """A message with no entities should still be published."""
        resolver = MagicMock()
        publisher = MagicMock()
        payload = dict(SAMPLE_PAYLOAD)
        payload["entities"] = []

        handle_message(payload, resolver, publisher)

        resolver.resolve.assert_not_called()
        publisher.publish.assert_called_once()

    @patch.dict("os.environ", {"RABBITMQ_URL": "", "REDIS_URL": ""}, clear=False)
    @patch("entity_resolver.__main__._setup_logging")
    def test_exits_when_rabbitmq_url_missing(self, mock_logging: MagicMock) -> None:
        """main() should sys.exit(1) when RABBITMQ_URL is not set."""
        import pytest

        from entity_resolver.__main__ import main

        with pytest.raises(SystemExit, match="1"):
            main()
