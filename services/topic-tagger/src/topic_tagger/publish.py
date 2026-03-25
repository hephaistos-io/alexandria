"""Publish classification results to a RabbitMQ fanout exchange.

Exchange: articles.classified (fanout)
Queues:
  articles.classified.store    — consumed by label-updater (writes to DB)
  articles.classified.relation — consumed by relation-extractor (writes to Neo4j)

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

DEFAULT_EXCHANGE = "articles.classified"
QUEUE_STORE = "articles.classified.store"
QUEUE_DOWNSTREAM = "articles.classified.relation"

MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY_SECONDS = 5


class RabbitMqPublisher:
    """Publishes classification result messages to a RabbitMQ fanout exchange.

    The fanout exchange fans out to all bound queues, so adding a new consumer
    later only requires declaring a new queue and binding — no changes here.

    Connection resilience: pika's BlockingConnection does not process heartbeats
    while the Python thread is blocked (e.g. during model inference). RabbitMQ
    will close connections that miss heartbeat deadlines, which causes
    StreamLostError on the next publish attempt. To handle this, publish()
    reconnects once on any connection error and retries the send.
    """

    def __init__(self, url: str, exchange: str = DEFAULT_EXCHANGE) -> None:
        self._url = url
        self._exchange = exchange
        self._connection: pika.BlockingConnection | None = None
        self._channel: (
            pika.adapters.blocking_connection.BlockingChannel | None
        ) = None
        self._connect()

    def _connect(self) -> None:
        """Open a connection, declare the exchange, and bind the downstream queues.

        Called at construction and on reconnect after a dropped connection.
        Declaring an already-existing exchange/queue with the same arguments
        is a no-op in RabbitMQ, so re-declaring on reconnect is safe.
        """
        params = pika.URLParameters(self._url)
        # Match the consumer's 600s heartbeat — the publisher connection also
        # sits idle during ML inference and would otherwise get killed.
        params.heartbeat = 600
        logger.info("Connecting to RabbitMQ at %s", params.host)
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()

        self._channel.exchange_declare(
            exchange=self._exchange,
            exchange_type="fanout",
            durable=True,
        )
        logger.info(
            "Exchange '%s' declared (fanout, durable=True)", self._exchange
        )

        for queue_name in (QUEUE_STORE, QUEUE_DOWNSTREAM):
            self._channel.queue_declare(queue=queue_name, durable=True)
            self._channel.queue_bind(
                queue=queue_name, exchange=self._exchange
            )
            logger.info(
                "Queue '%s' declared and bound to '%s'",
                queue_name,
                self._exchange,
            )

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
        """Send a message body to the exchange. Raises on connection failure."""
        if self._channel is None:
            raise pika.exceptions.AMQPConnectionError(
                "Channel is not open"
            )
        self._channel.basic_publish(
            exchange=self._exchange,
            routing_key="",
            body=body,
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent,
                content_type="application/json",
            ),
        )

    def publish(
        self,
        url: str,
        labels: list[dict],
        classified_at: str,
        entities: list[dict] | None = None,
        title: str = "",
        content: str = "",
    ) -> None:
        """Publish a classification result.

        Message shape:
            {
                "url": "https://...",
                "labels": [{"name": "CONFLICT", "score": 0.85}, ...],
                "classified_at": "2026-03-21T10:00:00Z",
                "entities": [{"text": "Iran", "label": "GPE", ...}, ...],
                "title": "...",
                "content": "..."
            }

        The title and content are passed through so that downstream consumers
        (e.g. relation-extractor) can access the article text without an
        extra database lookup.

        Reconnects once if the connection was dropped (e.g. due to a heartbeat
        timeout during model inference) before raising to the caller.
        """
        body = json.dumps({
            "url": url,
            "labels": labels,
            "classified_at": classified_at,
            "entities": entities,
            "title": title,
            "content": content,
        })
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
            "Published classification for body length %d", len(body)
        )

    def close(self) -> None:
        """Close the RabbitMQ connection."""
        if self._connection and self._connection.is_open:
            self._connection.close()
            logger.info("RabbitMQ connection closed")
