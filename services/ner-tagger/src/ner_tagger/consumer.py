"""RabbitMQ consumer — pulls messages from a queue and dispatches to a handler."""

import json
import logging
from collections.abc import Callable

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

logger = logging.getLogger(__name__)

DEFAULT_CONSUME_QUEUE = "articles.raw"


class MessageConsumer:
    """Consumes JSON messages from a RabbitMQ queue.

    Uses pika's basic_consume callback model: the broker pushes messages
    to us, and we ACK after processing. prefetch_count=1 keeps one message
    in-flight at a time — NER is CPU-bound, no benefit to buffering.
    """

    def __init__(
        self,
        url: str,
        on_message: Callable[[dict], None],
        queue: str = DEFAULT_CONSUME_QUEUE,
        prefetch_count: int = 1,
    ) -> None:
        self._queue = queue
        self._on_message = on_message

        params = pika.URLParameters(url)
        params.heartbeat = 600
        logger.info("Connecting to RabbitMQ at %s", params.host)
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()

        self._channel.queue_declare(queue=self._queue, durable=True)
        self._channel.basic_qos(prefetch_count=prefetch_count)

    def start(self) -> None:
        """Block forever, processing messages as they arrive."""
        logger.info("Waiting for messages on '%s'", self._queue)
        self._channel.basic_consume(
            queue=self._queue,
            on_message_callback=self._handle_delivery,
        )
        self._channel.start_consuming()

    def _handle_delivery(
        self,
        channel: BlockingChannel,
        method: Basic.Deliver,
        properties: BasicProperties,
        body: bytes,
    ) -> None:
        """Callback invoked by pika for each delivered message.

        Always ACKs — even on failure. NER failures (bad JSON, unexpected
        fields) won't succeed on retry, so leaving them unacked would
        poison the queue.
        """
        try:
            payload = json.loads(body)
            self._on_message(payload)
        except Exception:
            logger.exception(
                "Failed to process message: %s",
                body.decode("utf-8", errors="replace")[:200],
            )
        finally:
            channel.basic_ack(delivery_tag=method.delivery_tag)

    def close(self) -> None:
        """Close the RabbitMQ connection."""
        if self._connection and self._connection.is_open:
            self._connection.close()
            logger.info("RabbitMQ connection closed")
