import json
from unittest.mock import MagicMock, patch

import pika
import pika.exceptions
import pytest

from ner_tagger.models import TaggedArticle
from ner_tagger.publish import MAX_RECONNECT_ATTEMPTS, RabbitMqPublisher


def _make_tagged_article() -> TaggedArticle:
    return TaggedArticle(
        source="rss",
        origin="bbc_world",
        title="Test Article",
        url="https://example.com/test",
        summary="A summary.",
        published="2026-03-20T14:00:00+00:00",
        fetched_at="2026-03-20T14:30:00+00:00",
        content="Iran announced new sanctions against the United States.",
        scraped_at="2026-03-20T14:31:00+00:00",
        entities=[
            {"text": "Iran", "label": "GPE", "start": 0, "end": 4},
            {"text": "the United States", "label": "GPE", "start": 37, "end": 54},
        ],
        tagged_at="2026-03-20T14:32:00+00:00",
    )


@patch("ner_tagger.publish.pika.BlockingConnection")
class TestRabbitMqPublisher:
    def test_declares_durable_queue(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        RabbitMqPublisher("amqp://localhost:5672")
        mock_channel.queue_declare.assert_called_once_with(
            queue="articles.tagged", durable=True
        )

    def test_publish_body_is_valid_json(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_tagged_article())

        body = mock_channel.basic_publish.call_args.kwargs["body"]
        parsed = json.loads(body)
        assert parsed["title"] == "Test Article"
        assert parsed["content"] == "Iran announced new sanctions against the United States."
        assert parsed["tagged_at"] == "2026-03-20T14:32:00+00:00"

    def test_publish_body_contains_entities(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_tagged_article())

        body = mock_channel.basic_publish.call_args.kwargs["body"]
        parsed = json.loads(body)
        assert len(parsed["entities"]) == 2
        assert parsed["entities"][0]["text"] == "Iran"
        assert parsed["entities"][0]["label"] == "GPE"
        assert parsed["entities"][1]["text"] == "the United States"

    def test_publish_routes_to_articles_tagged(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_tagged_article())

        call_kwargs = mock_channel.basic_publish.call_args.kwargs
        assert call_kwargs["routing_key"] == "articles.tagged"
        assert call_kwargs["exchange"] == ""

    def test_publish_sets_persistent_delivery(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_tagged_article())

        props = mock_channel.basic_publish.call_args.kwargs["properties"]
        assert props.delivery_mode == pika.DeliveryMode.Persistent.value

    def test_publish_sets_json_content_type(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_tagged_article())

        props = mock_channel.basic_publish.call_args.kwargs["properties"]
        assert props.content_type == "application/json"

    def test_close_closes_open_connection(self, mock_conn_cls: MagicMock) -> None:
        mock_conn = mock_conn_cls.return_value
        mock_conn.is_open = True
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.close()
        mock_conn.close.assert_called_once()

    def test_reconnects_on_stream_lost_error(
        self, mock_conn_cls: MagicMock
    ) -> None:
        """StreamLostError on first publish triggers reconnect + retry."""
        mock_channel = mock_conn_cls.return_value.channel.return_value
        # First call raises, second (after reconnect) succeeds.
        mock_channel.basic_publish.side_effect = [
            pika.exceptions.StreamLostError("gone"),
            None,
        ]
        mock_conn_cls.return_value.is_closed = False

        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_tagged_article())

        # basic_publish called twice: original + retry
        assert mock_channel.basic_publish.call_count == 2

    def test_reconnects_on_amqp_connection_error(
        self, mock_conn_cls: MagicMock
    ) -> None:
        """AMQPConnectionError on first publish triggers reconnect + retry."""
        mock_channel = mock_conn_cls.return_value.channel.return_value
        mock_channel.basic_publish.side_effect = [
            pika.exceptions.AMQPConnectionError("refused"),
            None,
        ]
        mock_conn_cls.return_value.is_closed = False

        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_tagged_article())

        assert mock_channel.basic_publish.call_count == 2

    def test_retry_failure_propagates(self, mock_conn_cls: MagicMock) -> None:
        """If the retry publish also fails, the exception propagates."""
        mock_channel = mock_conn_cls.return_value.channel.return_value
        mock_channel.basic_publish.side_effect = [
            pika.exceptions.StreamLostError("gone"),
            pika.exceptions.StreamLostError("still gone"),
        ]
        mock_conn_cls.return_value.is_closed = False

        publisher = RabbitMqPublisher("amqp://localhost:5672")

        with pytest.raises(pika.exceptions.StreamLostError):
            publisher.publish(_make_tagged_article())


@patch("ner_tagger.publish.time.sleep")
@patch("ner_tagger.publish.pika.BlockingConnection")
class TestReconnect:
    def test_reconnect_retries_up_to_max(
        self, mock_conn_cls: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """_reconnect exhausts MAX_RECONNECT_ATTEMPTS then raises."""
        publisher = RabbitMqPublisher("amqp://localhost:5672")

        # After initial connect, make all subsequent connects fail.
        mock_conn_cls.side_effect = pika.exceptions.AMQPConnectionError(
            "down"
        )

        with pytest.raises(pika.exceptions.AMQPConnectionError):
            publisher._reconnect()

        assert mock_conn_cls.call_count == MAX_RECONNECT_ATTEMPTS + 1  # 1 init + N retries
        assert mock_sleep.call_count == MAX_RECONNECT_ATTEMPTS - 1

    def test_reconnect_succeeds_on_second_attempt(
        self, mock_conn_cls: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """_reconnect succeeds after one failed attempt."""
        publisher = RabbitMqPublisher("amqp://localhost:5672")

        # First reconnect attempt fails, second succeeds.
        mock_conn_cls.side_effect = [
            pika.exceptions.AMQPConnectionError("down"),
            MagicMock(),  # success
        ]
        mock_conn_cls.return_value.is_closed = True

        publisher._reconnect()

        # 2 attempts (1 fail + 1 success)
        assert mock_conn_cls.call_count == 3  # 1 init + 2 reconnect
        mock_sleep.assert_called_once()
