"""Publish NER-tagged articles to a RabbitMQ queue.

The publisher maintains its own pika connection, separate from the
consumer's connection.  This means its heartbeats are NOT processed
while the consumer blocks in start_consuming().  After a long idle
period (no messages to tag), RabbitMQ will kill the publisher's
connection due to missed heartbeats.

To handle this, publish() catches StreamLostError and reconnects
automatically — same pattern used by article-fetcher's publisher.
"""

import json
import logging
import time
from dataclasses import asdict

import pika
import pika.exceptions

from ner_tagger.models import TaggedArticle

logger = logging.getLogger(__name__)

DEFAULT_QUEUE = "articles.tagged"

MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY_SECONDS = 5


class RabbitMqPublisher:
    """Publishes TaggedArticle objects to a RabbitMQ queue as JSON.

    All fields in TaggedArticle are strings, dicts, or None — no custom
    JSON serializer needed.

    Reconnects automatically if the connection drops between publishes
    (e.g. due to missed heartbeats during idle periods).
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
        # The publisher sits idle between article batches (up to 60s between
        # RSS polls). The default heartbeat (~60s) causes RabbitMQ to kill the
        # connection for missed heartbeats during idle periods. 600s matches
        # the consumer's heartbeat and avoids unnecessary reconnects.
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
                    logger.error("Failed to reconnect after %d attempts", MAX_RECONNECT_ATTEMPTS)
                    raise

    def _publish_body(self, body: str, props: pika.BasicProperties) -> None:
        """Send a message body to the queue. Raises on connection failure."""
        if self._channel is None:
            raise pika.exceptions.AMQPConnectionError("Channel is not open")
        self._channel.basic_publish(
            exchange="",
            routing_key=self._queue,
            body=body,
            properties=props,
        )

    def publish(self, article: TaggedArticle) -> None:
        """Serialize a TaggedArticle to JSON and publish it.

        If the connection is dead (missed heartbeats during idle), reconnects
        and retries the publish once.
        """
        body = json.dumps(asdict(article))
        props = pika.BasicProperties(
            delivery_mode=pika.DeliveryMode.Persistent,
            content_type="application/json",
        )

        try:
            self._publish_body(body, props)
        except (
            pika.exceptions.StreamLostError,
            pika.exceptions.AMQPConnectionError,
        ):
            logger.warning("Connection lost during publish, reconnecting")
            self._reconnect()
            # Retry once after reconnect — also protected so failures
            # propagate cleanly instead of silently losing the message.
            self._publish_body(body, props)

        logger.debug(
            "Published: %s (%d entities)",
            article.url,
            len(article.entities),
        )

    def close(self) -> None:
        """Close the RabbitMQ connection."""
        if self._connection and self._connection.is_open:
            self._connection.close()
            logger.info("RabbitMQ connection closed")
