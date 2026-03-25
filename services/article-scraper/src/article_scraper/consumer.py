"""RabbitMQ consumer — pulls messages from a queue and dispatches to a handler."""

import json
import logging
import time
from collections.abc import Callable

import pika
import pika.exceptions
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

logger = logging.getLogger(__name__)

DEFAULT_CONSUME_QUEUE = "articles.rss"

MAX_CONNECT_ATTEMPTS = 5
CONNECT_RETRY_DELAY_SECONDS = 5


class MessageConsumer:
    """Consumes JSON messages from a RabbitMQ queue.

    Uses pika's basic_consume callback model: the broker pushes messages
    to us, and we ACK after processing. More efficient than polling with
    basic_get — no wasted cycles when the queue is empty.

    Usage:
        consumer = MessageConsumer("amqp://localhost:5672", on_message=handle)
        consumer.start()  # blocks forever
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
        self._prefetch_count = prefetch_count

        self._connection, self._channel = self._connect_with_retry(url)

    def _connect_with_retry(
        self, url: str,
    ) -> tuple[
        pika.BlockingConnection,
        BlockingChannel,
    ]:
        """Connect to RabbitMQ with retries.

        In containerized environments (Docker Compose, K8s) the scraper may
        start before RabbitMQ is healthy.  Rather than crashing immediately
        and relying on the orchestrator to restart us, we retry a few times.
        """
        params = pika.URLParameters(url)

        for attempt in range(1, MAX_CONNECT_ATTEMPTS + 1):
            try:
                logger.info("Connecting to RabbitMQ at %s", params.host)
                connection = pika.BlockingConnection(params)
                channel = connection.channel()

                # Must match the producer's queue declaration (durable=True).
                channel.queue_declare(queue=self._queue, durable=True)

                # prefetch_count=1: RabbitMQ delivers one message at a time.
                # Since we're single-threaded and scraping is slow (HTTP
                # fetch), there's no benefit to buffering more messages.
                channel.basic_qos(prefetch_count=self._prefetch_count)
                return connection, channel
            except pika.exceptions.AMQPConnectionError:
                if attempt < MAX_CONNECT_ATTEMPTS:
                    logger.warning(
                        "Connect attempt %d/%d failed, retrying in %ds",
                        attempt, MAX_CONNECT_ATTEMPTS,
                        CONNECT_RETRY_DELAY_SECONDS,
                    )
                    time.sleep(CONNECT_RETRY_DELAY_SECONDS)
                else:
                    logger.error(
                        "Failed to connect after %d attempts",
                        MAX_CONNECT_ATTEMPTS,
                    )
                    raise

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

        Always ACKs — even on failure. Failed extractions (404, timeout,
        empty content) won't succeed on retry, so leaving them unacked
        would poison the queue.
        """
        try:
            payload = json.loads(body)
            self._on_message(payload)
        except Exception:
            logger.exception(
                "Failed to process message: %s",
                body[:200].decode("utf-8", errors="replace"),
            )
        finally:
            channel.basic_ack(delivery_tag=method.delivery_tag)

    def close(self) -> None:
        """Close the RabbitMQ connection."""
        if self._connection and self._connection.is_open:
            self._connection.close()
            logger.info("RabbitMQ connection closed")
