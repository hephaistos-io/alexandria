import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pika
import pika.exceptions
import pytest

from article_fetcher.models import Article
from article_fetcher.publish import RabbitMqPublisher, _serialize_datetime


def _make_article() -> Article:
    return Article(
        source="rss",
        origin="test",
        title="Test Article",
        url="https://example.com/test",
        summary="A test summary.",
        published=datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 3, 20, 14, 30, tzinfo=timezone.utc),
    )


def _make_article_no_date() -> Article:
    return Article(
        source="rss",
        origin="test",
        title="No Date",
        url="https://example.com/no-date",
        summary="",
        published=None,
        fetched_at=datetime(2026, 3, 20, 14, 30, tzinfo=timezone.utc),
    )


class TestSerializeDatetime:
    def test_datetime_to_isoformat(self) -> None:
        dt = datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc)
        assert _serialize_datetime(dt) == "2026-03-20T14:00:00+00:00"

    def test_non_datetime_raises(self) -> None:
        with pytest.raises(TypeError):
            _serialize_datetime({"not": "a datetime"})


@patch("article_fetcher.publish.pika.BlockingConnection")
class TestRabbitMqPublisher:
    def test_declares_durable_queue(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        RabbitMqPublisher("amqp://localhost:5672")
        mock_channel.queue_declare.assert_called_once_with(queue="articles.rss", durable=True)

    def test_custom_queue_name(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        RabbitMqPublisher("amqp://localhost:5672", queue="custom_queue")
        mock_channel.queue_declare.assert_called_once_with(queue="custom_queue", durable=True)

    def test_publish_calls_basic_publish(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")

        publisher.publish(_make_article())

        mock_channel.basic_publish.assert_called_once()
        call_kwargs = mock_channel.basic_publish.call_args.kwargs
        assert call_kwargs["routing_key"] == "articles.rss"
        assert call_kwargs["exchange"] == ""

    def test_publish_body_is_valid_json(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_article())

        body = mock_channel.basic_publish.call_args.kwargs["body"]
        parsed = json.loads(body)
        assert parsed["title"] == "Test Article"
        assert parsed["url"] == "https://example.com/test"
        assert parsed["published"] == "2026-03-20T14:00:00+00:00"

    def test_publish_none_published_becomes_null(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_article_no_date())

        body = mock_channel.basic_publish.call_args.kwargs["body"]
        parsed = json.loads(body)
        assert parsed["published"] is None

    def test_publish_sets_persistent_delivery(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_article())

        props = mock_channel.basic_publish.call_args.kwargs["properties"]
        assert props.delivery_mode == pika.DeliveryMode.Persistent.value

    def test_publish_sets_json_content_type(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_article())

        props = mock_channel.basic_publish.call_args.kwargs["properties"]
        assert props.content_type == "application/json"

    def test_close_closes_open_connection(self, mock_conn_cls: MagicMock) -> None:
        mock_conn = mock_conn_cls.return_value
        mock_conn.is_open = True
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.close()
        mock_conn.close.assert_called_once()


@patch("article_fetcher.publish.pika.BlockingConnection")
class TestPublisherSleep:
    """Tests for the heartbeat-aware sleep method."""

    def test_sleep_delegates_to_connection_sleep(self, mock_conn_cls: MagicMock) -> None:
        mock_conn = mock_conn_cls.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")

        publisher.sleep(30)

        mock_conn.sleep.assert_called_once_with(30)

    def test_sleep_reconnects_on_stream_lost(self, mock_conn_cls: MagicMock) -> None:
        # First connection works, its sleep raises StreamLostError.
        first_conn = MagicMock()
        first_conn.sleep.side_effect = pika.exceptions.StreamLostError("gone")
        first_conn.is_closed = True

        # Second connection (after reconnect) works fine.
        second_conn = MagicMock()

        mock_conn_cls.side_effect = [first_conn, second_conn]

        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.sleep(60)

        # Should have connected twice (initial + reconnect).
        assert mock_conn_cls.call_count == 2
        # Sleep should be called on the new connection.
        second_conn.sleep.assert_called_once_with(60)


@patch("article_fetcher.publish.pika.BlockingConnection")
class TestPublisherReconnect:
    """Tests for reconnection on publish failure."""

    def test_publish_reconnects_on_stream_lost(self, mock_conn_cls: MagicMock) -> None:
        # First connection's channel raises StreamLostError on publish.
        first_conn = MagicMock()
        first_channel = MagicMock()
        first_channel.basic_publish.side_effect = pika.exceptions.StreamLostError("gone")
        first_conn.channel.return_value = first_channel
        first_conn.is_closed = True

        # Second connection works fine.
        second_conn = MagicMock()
        second_channel = MagicMock()
        second_conn.channel.return_value = second_channel

        mock_conn_cls.side_effect = [first_conn, second_conn]

        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_article())

        # Should have reconnected and retried the publish.
        assert mock_conn_cls.call_count == 2
        second_channel.basic_publish.assert_called_once()

    @patch("article_fetcher.publish.time.sleep")
    def test_reconnect_retries_on_failure(
        self, mock_time_sleep: MagicMock, mock_conn_cls: MagicMock
    ) -> None:
        # First connection works (initial connect).
        first_conn = MagicMock()
        first_channel = MagicMock()
        first_channel.basic_publish.side_effect = pika.exceptions.StreamLostError("gone")
        first_conn.channel.return_value = first_channel
        first_conn.is_closed = True

        # First reconnect attempt fails.
        # Second reconnect attempt succeeds.
        third_conn = MagicMock()
        third_channel = MagicMock()
        third_conn.channel.return_value = third_channel

        mock_conn_cls.side_effect = [
            first_conn,
            pika.exceptions.AMQPConnectionError("refused"),
            third_conn,
        ]

        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_article())

        # 3 connection attempts: initial + failed reconnect + successful reconnect.
        assert mock_conn_cls.call_count == 3
        # Should have slept between retry attempts.
        mock_time_sleep.assert_called()
        # Publish should succeed on the new connection.
        third_channel.basic_publish.assert_called_once()

    @patch("article_fetcher.publish.time.sleep")
    def test_reconnect_gives_up_after_max_attempts(
        self, mock_time_sleep: MagicMock, mock_conn_cls: MagicMock
    ) -> None:
        # Initial connection works.
        first_conn = MagicMock()
        first_channel = MagicMock()
        first_channel.basic_publish.side_effect = pika.exceptions.StreamLostError("gone")
        first_conn.channel.return_value = first_channel
        first_conn.is_closed = True

        # All reconnect attempts fail.
        mock_conn_cls.side_effect = [first_conn] + [
            pika.exceptions.AMQPConnectionError("refused") for _ in range(5)
        ]

        publisher = RabbitMqPublisher("amqp://localhost:5672")

        with pytest.raises(pika.exceptions.AMQPConnectionError):
            publisher.publish(_make_article())
