import json
from unittest.mock import MagicMock, patch

import pika
import pika.exceptions

from article_scraper.models import ScrapedArticle
from article_scraper.publish import (
    DEFAULT_EXCHANGE,
    QUEUE_RAW,
    QUEUE_TRAINING,
    RECONNECT_DELAY_SECONDS,
    RabbitMqPublisher,
)


def _make_scraped_article() -> ScrapedArticle:
    return ScrapedArticle(
        source="rss",
        origin="bbc_world",
        title="Test Article",
        url="https://example.com/test",
        summary="A summary.",
        published="2026-03-20T14:00:00+00:00",
        fetched_at="2026-03-20T14:30:00+00:00",
        content="Full article text extracted by trafilatura.",
        scraped_at="2026-03-20T14:31:00+00:00",
    )


@patch("article_scraper.publish.pika.BlockingConnection")
class TestRabbitMqPublisher:
    def test_no_connection_on_init(self, mock_conn_cls: MagicMock) -> None:
        """Constructor stores config but does not open a connection."""
        RabbitMqPublisher("amqp://localhost:5672")
        mock_conn_cls.assert_not_called()

    def test_declares_fanout_exchange(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_scraped_article())
        mock_channel.exchange_declare.assert_called_once_with(
            exchange=DEFAULT_EXCHANGE,
            exchange_type="fanout",
            durable=True,
        )

    def test_declares_both_queues_as_durable(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_scraped_article())
        mock_channel.queue_declare.assert_any_call(queue=QUEUE_RAW, durable=True)
        mock_channel.queue_declare.assert_any_call(queue=QUEUE_TRAINING, durable=True)
        assert mock_channel.queue_declare.call_count == 2

    def test_binds_both_queues_to_exchange(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_scraped_article())
        mock_channel.queue_bind.assert_any_call(queue=QUEUE_RAW, exchange=DEFAULT_EXCHANGE)
        mock_channel.queue_bind.assert_any_call(queue=QUEUE_TRAINING, exchange=DEFAULT_EXCHANGE)
        assert mock_channel.queue_bind.call_count == 2

    def test_publish_targets_fanout_exchange_with_empty_routing_key(
        self, mock_conn_cls: MagicMock
    ) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_scraped_article())

        call_kwargs = mock_channel.basic_publish.call_args.kwargs
        assert call_kwargs["exchange"] == DEFAULT_EXCHANGE
        assert call_kwargs["routing_key"] == ""

    def test_publish_body_is_valid_json(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_scraped_article())

        body = mock_channel.basic_publish.call_args.kwargs["body"]
        parsed = json.loads(body)
        assert parsed["title"] == "Test Article"
        assert parsed["content"] == "Full article text extracted by trafilatura."
        assert parsed["scraped_at"] == "2026-03-20T14:31:00+00:00"

    def test_publish_sets_persistent_delivery(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_scraped_article())

        props = mock_channel.basic_publish.call_args.kwargs["properties"]
        assert props.delivery_mode == pika.DeliveryMode.Persistent.value

    def test_publish_sets_json_content_type(self, mock_conn_cls: MagicMock) -> None:
        mock_channel = mock_conn_cls.return_value.channel.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_scraped_article())

        props = mock_channel.basic_publish.call_args.kwargs["properties"]
        assert props.content_type == "application/json"

    def test_closes_connection_after_publish(self, mock_conn_cls: MagicMock) -> None:
        """Each publish opens and closes its own connection."""
        mock_conn = mock_conn_cls.return_value
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_scraped_article())
        mock_conn.close.assert_called_once()

    @patch("article_scraper.publish.time.sleep")
    def test_retries_on_connection_error(
        self, mock_sleep: MagicMock, mock_conn_cls: MagicMock,
    ) -> None:
        """First connection attempt fails, second succeeds."""
        mock_conn_ok = MagicMock()
        mock_conn_cls.side_effect = [
            pika.exceptions.AMQPConnectionError("refused"),
            mock_conn_ok,
        ]
        publisher = RabbitMqPublisher("amqp://localhost:5672")
        publisher.publish(_make_scraped_article())

        assert mock_conn_cls.call_count == 2
        mock_conn_ok.channel.return_value.basic_publish.assert_called_once()
        mock_sleep.assert_called_once_with(RECONNECT_DELAY_SECONDS)

    def test_connect_closes_connection_on_declaration_failure(
        self, mock_conn_cls: MagicMock,
    ) -> None:
        """If exchange_declare fails, the connection is still closed."""
        mock_conn = mock_conn_cls.return_value
        mock_channel = mock_conn.channel.return_value
        mock_channel.exchange_declare.side_effect = RuntimeError(
            "exchange exists with different type"
        )

        publisher = RabbitMqPublisher("amqp://localhost:5672")
        try:
            publisher.publish(_make_scraped_article())
        except RuntimeError:
            pass

        # The connection opened by _connect() should be closed even
        # though exchange_declare failed.
        mock_conn.close.assert_called()
