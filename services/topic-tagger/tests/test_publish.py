"""Tests for the RabbitMQ publisher — serialization, reconnect, close."""

import json
from unittest.mock import MagicMock, patch

import pika
import pika.exceptions
import pytest

from topic_tagger.publish import MAX_RECONNECT_ATTEMPTS, RabbitMqPublisher


@patch("topic_tagger.publish.pika.BlockingConnection")
class TestRabbitMqPublisher:
    def test_declares_fanout_exchange(
        self, mock_conn_cls: MagicMock
    ) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        RabbitMqPublisher("amqp://localhost:5672")
        mock_channel.exchange_declare.assert_called_once_with(
            exchange="articles.classified",
            exchange_type="fanout",
            durable=True,
        )

    def test_declares_and_binds_queues(
        self, mock_conn_cls: MagicMock
    ) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        RabbitMqPublisher("amqp://localhost:5672")
        declared = [
            c.kwargs["queue"]
            for c in mock_channel.queue_declare.call_args_list
        ]
        assert "articles.classified.store" in declared
        assert "articles.classified.relation" in declared
        assert mock_channel.queue_bind.call_count == 2

    def test_publish_body_is_valid_json(
        self, mock_conn_cls: MagicMock
    ) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(
            url="https://example.com",
            labels=[{"name": "CONFLICT", "score": 0.9}],
            classified_at="2026-03-24T00:00:00Z",
        )

        body = mock_channel.basic_publish.call_args.kwargs["body"]
        parsed = json.loads(body)
        assert parsed["url"] == "https://example.com"
        assert parsed["labels"][0]["name"] == "CONFLICT"

    def test_publish_sets_persistent_delivery(
        self, mock_conn_cls: MagicMock
    ) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(
            url="https://example.com", labels=[], classified_at="t"
        )

        props = mock_channel.basic_publish.call_args.kwargs["properties"]
        assert props.delivery_mode == pika.DeliveryMode.Persistent.value

    def test_publish_sets_json_content_type(
        self, mock_conn_cls: MagicMock
    ) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(
            url="https://example.com", labels=[], classified_at="t"
        )

        props = mock_channel.basic_publish.call_args.kwargs["properties"]
        assert props.content_type == "application/json"

    def test_publish_routes_to_exchange(
        self, mock_conn_cls: MagicMock
    ) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(
            url="https://example.com", labels=[], classified_at="t"
        )

        kwargs = mock_channel.basic_publish.call_args.kwargs
        assert kwargs["exchange"] == "articles.classified"
        assert kwargs["routing_key"] == ""

    def test_close_closes_open_connection(
        self, mock_conn_cls: MagicMock
    ) -> None:
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
        mock_channel.basic_publish.side_effect = [
            pika.exceptions.StreamLostError("gone"),
            None,
        ]
        mock_conn_cls.return_value.is_closed = False

        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(
            url="https://example.com", labels=[], classified_at="t"
        )

        assert mock_channel.basic_publish.call_count == 2

    def test_retry_failure_propagates(
        self, mock_conn_cls: MagicMock
    ) -> None:
        """If the retry publish also fails, the exception propagates."""
        mock_channel = mock_conn_cls.return_value.channel.return_value
        mock_channel.basic_publish.side_effect = [
            pika.exceptions.StreamLostError("gone"),
            pika.exceptions.StreamLostError("still gone"),
        ]
        mock_conn_cls.return_value.is_closed = False

        publisher = RabbitMqPublisher("amqp://localhost:5672")

        with pytest.raises(pika.exceptions.StreamLostError):
            publisher.publish(
                url="https://example.com", labels=[], classified_at="t"
            )


@patch("topic_tagger.publish.time.sleep")
@patch("topic_tagger.publish.pika.BlockingConnection")
class TestPublisherReconnect:
    def test_reconnect_retries_up_to_max(
        self, mock_conn_cls: MagicMock, mock_sleep: MagicMock
    ) -> None:
        publisher = RabbitMqPublisher("amqp://localhost:5672")

        mock_conn_cls.side_effect = pika.exceptions.AMQPConnectionError(
            "down"
        )

        with pytest.raises(pika.exceptions.AMQPConnectionError):
            publisher._reconnect()

        # 1 init + MAX_RECONNECT_ATTEMPTS retries
        assert mock_conn_cls.call_count == MAX_RECONNECT_ATTEMPTS + 1
        assert mock_sleep.call_count == MAX_RECONNECT_ATTEMPTS - 1

    def test_reconnect_succeeds_on_second_attempt(
        self, mock_conn_cls: MagicMock, mock_sleep: MagicMock
    ) -> None:
        publisher = RabbitMqPublisher("amqp://localhost:5672")

        mock_conn_cls.side_effect = [
            pika.exceptions.AMQPConnectionError("down"),
            MagicMock(),
        ]
        mock_conn_cls.return_value.is_closed = True

        publisher._reconnect()

        assert mock_conn_cls.call_count == 3
        mock_sleep.assert_called_once()
