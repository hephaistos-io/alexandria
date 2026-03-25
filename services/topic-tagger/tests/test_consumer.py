"""Tests for the RabbitMQ consumer — connection setup, delivery handling, reconnect."""

import json
from unittest.mock import MagicMock, patch

import pika.exceptions
import pytest

from topic_tagger.consumer import MAX_RECONNECT_ATTEMPTS, MessageConsumer


@patch("topic_tagger.consumer.pika.BlockingConnection")
class TestMessageConsumer:
    def test_declares_durable_queue(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        MessageConsumer("amqp://localhost:5672", on_message=lambda x: None)
        mock_channel.queue_declare.assert_called_once_with(
            queue="articles.role-classified", durable=True
        )

    def test_custom_queue_name(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        MessageConsumer(
            "amqp://localhost:5672",
            on_message=lambda x: None,
            queue="custom",
        )
        mock_channel.queue_declare.assert_called_once_with(
            queue="custom", durable=True
        )

    def test_sets_prefetch_count(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        MessageConsumer(
            "amqp://localhost:5672",
            on_message=lambda x: None,
            prefetch_count=3,
        )
        mock_channel.basic_qos.assert_called_once_with(prefetch_count=3)

    def test_registers_basic_consume_in_connect(
        self, mock_conn_cls: MagicMock
    ) -> None:
        """basic_consume is registered inside _connect, not in start()."""
        mock_channel = mock_conn_cls.return_value.channel.return_value
        MessageConsumer("amqp://localhost:5672", on_message=lambda x: None)
        mock_channel.basic_consume.assert_called_once()

    def test_handle_delivery_calls_on_message(
        self, mock_conn_cls: MagicMock
    ) -> None:
        collected: list[dict] = []
        consumer = MessageConsumer(
            "amqp://localhost:5672", on_message=collected.append
        )

        mock_channel = MagicMock()
        mock_method = MagicMock()
        mock_method.delivery_tag = 1
        body = json.dumps({"url": "https://example.com"}).encode()

        consumer._handle_delivery(
            mock_channel, mock_method, MagicMock(), body
        )

        assert len(collected) == 1
        assert collected[0]["url"] == "https://example.com"
        mock_channel.basic_ack.assert_called_once_with(delivery_tag=1)

    def test_handle_delivery_acks_on_handler_exception(
        self, mock_conn_cls: MagicMock
    ) -> None:
        def exploding_handler(msg: dict) -> None:
            raise ValueError("boom")

        consumer = MessageConsumer(
            "amqp://localhost:5672", on_message=exploding_handler
        )
        mock_channel = MagicMock()
        mock_method = MagicMock()
        mock_method.delivery_tag = 42
        body = json.dumps({"url": "https://example.com"}).encode()

        consumer._handle_delivery(
            mock_channel, mock_method, MagicMock(), body
        )

        mock_channel.basic_ack.assert_called_once_with(delivery_tag=42)

    def test_handle_delivery_acks_on_invalid_json(
        self, mock_conn_cls: MagicMock
    ) -> None:
        consumer = MessageConsumer(
            "amqp://localhost:5672", on_message=lambda x: None
        )
        mock_channel = MagicMock()
        mock_method = MagicMock()
        mock_method.delivery_tag = 99

        consumer._handle_delivery(
            mock_channel, mock_method, MagicMock(), b"not json"
        )

        mock_channel.basic_ack.assert_called_once_with(delivery_tag=99)

    def test_handle_delivery_reraises_stream_lost_error(
        self, mock_conn_cls: MagicMock
    ) -> None:
        """StreamLostError must propagate so start() can reconnect."""
        def handler(msg: dict) -> None:
            raise pika.exceptions.StreamLostError("gone")

        consumer = MessageConsumer(
            "amqp://localhost:5672", on_message=handler
        )
        mock_channel = MagicMock()
        mock_method = MagicMock()
        mock_method.delivery_tag = 1
        body = json.dumps({"url": "https://example.com"}).encode()

        with pytest.raises(pika.exceptions.StreamLostError):
            consumer._handle_delivery(
                mock_channel, mock_method, MagicMock(), body
            )

        mock_channel.basic_ack.assert_not_called()


@patch("topic_tagger.consumer.time.sleep")
@patch("topic_tagger.consumer.pika.BlockingConnection")
class TestReconnect:
    def test_reconnect_retries_up_to_max(
        self, mock_conn_cls: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """_reconnect exhausts MAX_RECONNECT_ATTEMPTS then raises."""
        consumer = MessageConsumer(
            "amqp://localhost:5672", on_message=lambda x: None
        )

        mock_conn_cls.side_effect = pika.exceptions.AMQPConnectionError(
            "down"
        )

        with pytest.raises(pika.exceptions.AMQPConnectionError):
            consumer._reconnect()

        # 1 initial connect + MAX_RECONNECT_ATTEMPTS retries
        assert mock_conn_cls.call_count == MAX_RECONNECT_ATTEMPTS + 1
        assert mock_sleep.call_count == MAX_RECONNECT_ATTEMPTS

    def test_reconnect_succeeds_on_second_attempt(
        self, mock_conn_cls: MagicMock, mock_sleep: MagicMock
    ) -> None:
        consumer = MessageConsumer(
            "amqp://localhost:5672", on_message=lambda x: None
        )

        mock_conn_cls.side_effect = [
            pika.exceptions.AMQPConnectionError("down"),
            MagicMock(),  # success
        ]

        consumer._reconnect()

        # 1 init + 2 reconnect attempts (1 fail + 1 success)
        assert mock_conn_cls.call_count == 3
        assert mock_sleep.call_count == 2
