import json
from unittest.mock import MagicMock, patch

from article_scraper.consumer import MessageConsumer


@patch("article_scraper.consumer.pika.BlockingConnection")
class TestMessageConsumer:
    def test_declares_durable_queue(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        MessageConsumer("amqp://localhost:5672", on_message=lambda x: None)
        mock_channel.queue_declare.assert_called_once_with(
            queue="articles.rss", durable=True
        )

    def test_custom_queue_name(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        MessageConsumer(
            "amqp://localhost:5672", on_message=lambda x: None, queue="custom"
        )
        mock_channel.queue_declare.assert_called_once_with(queue="custom", durable=True)

    def test_sets_prefetch_count(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        MessageConsumer(
            "amqp://localhost:5672", on_message=lambda x: None, prefetch_count=3
        )
        mock_channel.basic_qos.assert_called_once_with(prefetch_count=3)

    def test_handle_delivery_calls_on_message(self, mock_conn_cls: MagicMock) -> None:
        collected: list[dict] = []
        consumer = MessageConsumer("amqp://localhost:5672", on_message=collected.append)

        mock_channel = MagicMock()
        mock_method = MagicMock()
        mock_method.delivery_tag = 1
        body = json.dumps({"url": "https://example.com"}).encode()

        consumer._handle_delivery(mock_channel, mock_method, MagicMock(), body)

        assert len(collected) == 1
        assert collected[0]["url"] == "https://example.com"
        mock_channel.basic_ack.assert_called_once_with(delivery_tag=1)

    def test_handle_delivery_acks_on_handler_exception(
        self, mock_conn_cls: MagicMock
    ) -> None:
        def exploding_handler(msg: dict) -> None:
            raise ValueError("boom")

        consumer = MessageConsumer("amqp://localhost:5672", on_message=exploding_handler)
        mock_channel = MagicMock()
        mock_method = MagicMock()
        mock_method.delivery_tag = 42
        body = json.dumps({"url": "https://example.com"}).encode()

        consumer._handle_delivery(mock_channel, mock_method, MagicMock(), body)

        # Must still ACK even though the handler raised
        mock_channel.basic_ack.assert_called_once_with(delivery_tag=42)

    def test_handle_delivery_acks_on_invalid_json(
        self, mock_conn_cls: MagicMock
    ) -> None:
        consumer = MessageConsumer("amqp://localhost:5672", on_message=lambda x: None)
        mock_channel = MagicMock()
        mock_method = MagicMock()
        mock_method.delivery_tag = 99

        consumer._handle_delivery(mock_channel, mock_method, MagicMock(), b"not json")

        mock_channel.basic_ack.assert_called_once_with(delivery_tag=99)
