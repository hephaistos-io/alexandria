"""Tests for the RabbitMQ publisher — serialization, reconnect, close."""

import json
from unittest.mock import MagicMock, patch

import pika
import pika.exceptions
import pytest

from role_classifier.publish import MAX_RECONNECT_ATTEMPTS, RabbitMqPublisher


@patch("role_classifier.publish.pika.BlockingConnection")
class TestRabbitMqPublisher:
    def test_declares_durable_queue(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        RabbitMqPublisher("amqp://localhost:5672")
        mock_channel.queue_declare.assert_called_once_with(
            queue="articles.role-classified", durable=True
        )

    def test_publish_body_is_valid_json(
        self, mock_conn_cls: MagicMock
    ) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish({"url": "https://example.com", "title": "Test"})

        body = mock_channel.basic_publish.call_args.kwargs["body"]
        parsed = json.loads(body)
        assert parsed["url"] == "https://example.com"
        assert parsed["title"] == "Test"

    def test_publish_sets_persistent_delivery(
        self, mock_conn_cls: MagicMock
    ) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish({"url": "https://example.com"})

        props = mock_channel.basic_publish.call_args.kwargs["properties"]
        assert props.delivery_mode == pika.DeliveryMode.Persistent.value

    def test_publish_sets_json_content_type(
        self, mock_conn_cls: MagicMock
    ) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish({"url": "https://example.com"})

        props = mock_channel.basic_publish.call_args.kwargs["properties"]
        assert props.content_type == "application/json"

    def test_publish_routes_to_correct_queue(
        self, mock_conn_cls: MagicMock
    ) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish({"url": "https://example.com"})

        kwargs = mock_channel.basic_publish.call_args.kwargs
        assert kwargs["routing_key"] == "articles.role-classified"
        assert kwargs["exchange"] == ""

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
        publisher.publish({"url": "https://example.com"})

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
            publisher.publish({"url": "https://example.com"})


@patch("role_classifier.publish.time.sleep")
@patch("role_classifier.publish.pika.BlockingConnection")
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
