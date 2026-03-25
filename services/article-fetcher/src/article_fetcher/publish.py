"""Publish articles to a RabbitMQ queue."""

import json
import logging
import time
from dataclasses import asdict
from datetime import datetime

import pika
import pika.exceptions

from article_fetcher.models import Article

logger = logging.getLogger(__name__)

DEFAULT_QUEUE = "articles.rss"

# Reconnection settings
MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY_SECONDS = 5


def _serialize_datetime(obj: object) -> str:
    """json.dumps default handler for datetime objects.

    datetime isn't JSON-serializable out of the box. This converts it to
    ISO 8601 format (e.g. "2026-03-20T14:30:00+00:00"), which is
    unambiguous and easy to parse on the consumer side.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


class RabbitMqPublisher:
    """Publishes Article objects to a RabbitMQ queue as JSON messages.

    Designed to be used as the on_article callback for FetchLoop:

        publisher = RabbitMqPublisher("amqp://guest:guest@localhost:5672")
        loop = FetchLoop(fetcher, on_article=publisher.publish)

    Creates a single long-lived connection and channel.  If the connection
    drops (network blip, broker restart, heartbeat timeout), the publisher
    will automatically reconnect on the next publish() or sleep() call.
    """

    def __init__(self, url: str, queue: str = DEFAULT_QUEUE) -> None:
        self._url = url
        self._queue = queue
        self._connection: pika.BlockingConnection | None = None
        self._channel: pika.adapters.blocking_connection.BlockingChannel | None = None
        self._connect()

    def _connect(self) -> None:
        """Open a fresh connection and channel, declare the queue."""
        params = pika.URLParameters(self._url)
        logger.info("Connecting to RabbitMQ at %s", params.host)
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()

        # Declare the queue as durable so it survives broker restarts.
        # If the queue already exists with these settings, this is a no-op.
        self._channel.queue_declare(queue=self._queue, durable=True)
        logger.info("Queue '%s' declared (durable=True)", self._queue)

    def _reconnect(self) -> None:
        """Close any stale connection and open a new one.

        Retries up to MAX_RECONNECT_ATTEMPTS times with a fixed delay.
        Uses time.sleep() for the retry delay because we have no live
        connection to call connection.sleep() on.
        """
        for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
            logger.warning(
                "Reconnecting to RabbitMQ (attempt %d/%d)",
                attempt,
                MAX_RECONNECT_ATTEMPTS,
            )
            try:
                # Clean up the old connection if it's still around.
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
                    logger.error("Failed to reconnect after %d attempts", MAX_RECONNECT_ATTEMPTS)
                    raise

    def publish(self, article: Article) -> None:
        """Serialize an Article to JSON and publish it to the queue.

        Matches the Callable[[Article], None] signature that FetchLoop expects.
        If the connection is dead, attempts to reconnect before publishing.
        """
        body = json.dumps(asdict(article), default=_serialize_datetime)

        if self._channel is None:
            self._reconnect()

        try:
            self._channel.basic_publish(  # type: ignore[union-attr]
                exchange="",  # default exchange — routes by queue name
                routing_key=self._queue,
                body=body,
                properties=pika.BasicProperties(
                    delivery_mode=pika.DeliveryMode.Persistent,
                    content_type="application/json",
                ),
            )
        except (pika.exceptions.StreamLostError, pika.exceptions.AMQPConnectionError):
            logger.warning("Connection lost during publish, reconnecting")
            self._reconnect()
            # Retry the publish once after reconnecting.
            self._channel.basic_publish(  # type: ignore[union-attr]
                exchange="",
                routing_key=self._queue,
                body=body,
                properties=pika.BasicProperties(
                    delivery_mode=pika.DeliveryMode.Persistent,
                    content_type="application/json",
                ),
            )
        logger.debug("Published: %s", article.url)

    def sleep(self, seconds: float) -> None:
        """Sleep while keeping the AMQP connection alive.

        Delegates to connection.sleep(), which processes I/O events
        (including heartbeat frames) while waiting.  This is the key
        difference from time.sleep() — it prevents RabbitMQ from
        killing the connection due to missed heartbeats.

        If the connection has already dropped, reconnects first.
        """
        if self._connection is None:
            self._reconnect()

        try:
            self._connection.sleep(seconds)  # type: ignore[union-attr]
        except (pika.exceptions.StreamLostError, pika.exceptions.AMQPConnectionError):
            logger.warning("Connection lost during sleep, reconnecting")
            self._reconnect()
            # After reconnecting, sleep the remaining time.  We don't
            # track how much time already elapsed — close enough.
            self._connection.sleep(seconds)  # type: ignore[union-attr]

    def close(self) -> None:
        """Close the RabbitMQ connection."""
        if self._connection and self._connection.is_open:
            self._connection.close()
            logger.info("RabbitMQ connection closed")
