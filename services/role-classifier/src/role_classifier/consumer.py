"""RabbitMQ consumer — pulls messages from the articles.resolved queue.

Reconnects automatically on StreamLostError (caused by RabbitMQ dropping the
connection when heartbeats are missed during long-running ML inference).
"""

import json
import logging
import time
from collections.abc import Callable

import pika
import pika.exceptions
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

logger = logging.getLogger(__name__)

DEFAULT_CONSUME_QUEUE = "articles.resolved"

RECONNECT_DELAY_SECONDS = 5
MAX_RECONNECT_ATTEMPTS = 10


class MessageConsumer:
    """Consumes JSON messages from a RabbitMQ queue.

    Connection resilience: pika's BlockingConnection does not process heartbeats
    while the Python thread is blocked (e.g. during model inference). If the
    broker drops the connection during that window, start_consuming() raises
    StreamLostError. start() catches that and reconnects so the service keeps
    running without a full process restart.
    """

    def __init__(
        self,
        url: str,
        on_message: Callable[[dict], None],
        queue: str = DEFAULT_CONSUME_QUEUE,
        prefetch_count: int = 1,
    ) -> None:
        self._url = url
        self._queue = queue
        self._on_message = on_message
        self._prefetch_count = prefetch_count
        self._connection: pika.BlockingConnection | None = None
        self._channel: BlockingChannel | None = None
        self._connect()

    def _connect(self) -> None:
        """Open a fresh connection, set up the channel, and register consumer.

        Called at construction and after every dropped connection. Registering
        basic_consume here (rather than in start()) ensures it's always paired
        with a fresh channel and avoids duplicate consumer registration.
        """
        params = pika.URLParameters(self._url)
        # ML inference blocks the thread for 20–60s per article, during which
        # pika can't send heartbeats.  A 600s heartbeat gives plenty of room
        # so RabbitMQ won't kill the connection mid-inference.
        params.heartbeat = 600
        logger.info("Connecting to RabbitMQ at %s", params.host)
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()

        self._channel.queue_declare(queue=self._queue, durable=True)
        self._channel.basic_qos(prefetch_count=self._prefetch_count)
        self._channel.basic_consume(
            queue=self._queue,
            on_message_callback=self._handle_delivery,
        )

    def _reconnect(self) -> None:
        """Reconnect with retry loop. Raises after MAX_RECONNECT_ATTEMPTS."""
        for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
            logger.warning(
                "Reconnecting to RabbitMQ (attempt %d/%d)",
                attempt,
                MAX_RECONNECT_ATTEMPTS,
            )
            time.sleep(RECONNECT_DELAY_SECONDS)
            try:
                self._connect()
                logger.info("Reconnected to RabbitMQ successfully")
                return
            except pika.exceptions.AMQPConnectionError:
                if attempt == MAX_RECONNECT_ATTEMPTS:
                    logger.error(
                        "Failed to reconnect after %d attempts",
                        MAX_RECONNECT_ATTEMPTS,
                    )
                    raise

    def start(self) -> None:
        """Block forever, processing messages as they arrive.

        Wraps start_consuming in a reconnect loop so that a dropped
        connection (StreamLostError) doesn't kill the process.
        """
        while True:
            try:
                logger.info("Waiting for messages on '%s'", self._queue)
                self._channel.start_consuming()
            except (
                pika.exceptions.StreamLostError,
                pika.exceptions.AMQPConnectionError,
            ) as exc:
                logger.warning("Connection lost (%s), reconnecting", exc)
                self._reconnect()

    def _handle_delivery(
        self,
        channel: BlockingChannel,
        method: Basic.Deliver,
        properties: BasicProperties,
        body: bytes,
    ) -> None:
        """Callback invoked by pika for each delivered message.

        Re-raises connection errors so they reach the reconnect loop in start().
        All other exceptions are logged and the message is ACKed to avoid
        poisoning the queue (bad JSON or unexpected fields won't succeed on retry).
        """
        try:
            payload = json.loads(body)
            self._on_message(payload)
        except (
            pika.exceptions.StreamLostError,
            pika.exceptions.AMQPConnectionError,
        ):
            raise
        except Exception:
            logger.exception(
                "Failed to process message: %s",
                body.decode("utf-8", errors="replace")[:200],
            )

        channel.basic_ack(delivery_tag=method.delivery_tag)

    def close(self) -> None:
        """Close the RabbitMQ connection."""
        if self._connection and self._connection.is_open:
            self._connection.close()
            logger.info("RabbitMQ connection closed")
