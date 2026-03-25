"""Publish role-classified articles to a RabbitMQ queue.

Queue: articles.role-classified (simple queue, not a fanout exchange)

The publisher maintains its own pika connection, separate from the
consumer's connection. This means its heartbeats are NOT processed
while the consumer blocks in start_consuming(). After a long idle
period, RabbitMQ will kill the publisher's connection due to missed
heartbeats.

To handle this, publish() catches StreamLostError and reconnects
automatically before retrying the send.
"""

import json
import logging
import time

import pika
import pika.exceptions

logger = logging.getLogger(__name__)

DEFAULT_QUEUE = "articles.role-classified"

MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY_SECONDS = 5


class RabbitMqPublisher:
    """Publishes role-classified article payloads to a RabbitMQ queue.

    Uses a simple queue (not a fanout exchange) — the downstream consumer
    reads directly from articles.role-classified.

    Reconnects on StreamLostError or AMQPConnectionError, which covers
    the common case of RabbitMQ closing an idle connection due to missed
    heartbeats while ML inference was running.
    """

    def __init__(self, url: str, queue: str = DEFAULT_QUEUE) -> None:
        self._url = url
        self._queue = queue
        self._connection: pika.BlockingConnection | None = None
        self._channel: (
            pika.adapters.blocking_connection.BlockingChannel | None
        ) = None
        self._connect()

    def _connect(self) -> None:
        """Open a connection and declare the queue.

        Called at construction and on reconnect after a dropped connection.
        Declaring an already-existing queue with the same arguments is a
        no-op in RabbitMQ, so re-declaring on reconnect is safe.
        """
        params = pika.URLParameters(self._url)
        # Match the consumer's 600s heartbeat — the publisher connection also
        # sits idle during ML inference and would otherwise get killed.
        params.heartbeat = 600
        logger.info("Connecting to RabbitMQ at %s", params.host)
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()
        self._channel.queue_declare(queue=self._queue, durable=True)
        logger.info("Queue '%s' declared (durable=True)", self._queue)

    def _reconnect(self) -> None:
        """Close any stale connection and open a new one.

        Retries up to MAX_RECONNECT_ATTEMPTS times with a fixed delay.
        """
        for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
            logger.warning(
                "Reconnecting to RabbitMQ (attempt %d/%d)",
                attempt,
                MAX_RECONNECT_ATTEMPTS,
            )
            try:
                if self._connection and not self._connection.is_closed:
                    try:
                        self._connection.close()
                    except Exception:
                        pass
                self._connect()
                logger.info("Reconnected to RabbitMQ successfully")
                return
            except pika.exceptions.AMQPConnectionError:
                if attempt < MAX_RECONNECT_ATTEMPTS:
                    logger.warning(
                        "Reconnect attempt %d failed, retrying in %ds",
                        attempt,
                        RECONNECT_DELAY_SECONDS,
                    )
                    time.sleep(RECONNECT_DELAY_SECONDS)
                else:
                    logger.error(
                        "Failed to reconnect after %d attempts",
                        MAX_RECONNECT_ATTEMPTS,
                    )
                    raise

    def _do_publish(self, body: str) -> None:
        """Send a message body to the queue. Raises on connection failure."""
        if self._channel is None:
            raise pika.exceptions.AMQPConnectionError(
                "Channel is not open"
            )
        self._channel.basic_publish(
            exchange="",
            routing_key=self._queue,
            body=body,
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent,
                content_type="application/json",
            ),
        )

    def publish(self, payload: dict) -> None:
        """Publish a role-classified article payload as JSON.

        Reconnects and retries once if the connection was dropped.
        """
        body = json.dumps(payload)
        try:
            self._do_publish(body)
        except (
            pika.exceptions.StreamLostError,
            pika.exceptions.AMQPConnectionError,
        ):
            logger.warning(
                "Publisher connection lost — reconnecting and retrying"
            )
            self._reconnect()
            self._do_publish(body)

        logger.debug(
            "Published to '%s' (body length %d)", self._queue, len(body)
        )

    def close(self) -> None:
        """Close the RabbitMQ connection."""
        if self._connection and self._connection.is_open:
            self._connection.close()
            logger.info("RabbitMQ connection closed")
