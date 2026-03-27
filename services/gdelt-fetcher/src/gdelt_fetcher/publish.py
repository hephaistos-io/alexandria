"""Publish conflict events to a RabbitMQ queue."""

import json
import logging
import time
from dataclasses import asdict
from datetime import datetime

import pika
import pika.exceptions

from gdelt_fetcher.models import ConflictEvent

logger = logging.getLogger(__name__)

DEFAULT_QUEUE = "conflict_events.raw"

MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY_SECONDS = 5


def _serialize_datetime(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


class RabbitMqPublisher:
    """Publishes ConflictEvent objects to a RabbitMQ queue as JSON messages.

    Creates a single long-lived connection and channel. If the connection
    drops, the publisher reconnects automatically on the next call.
    """

    def __init__(self, url: str, queue: str = DEFAULT_QUEUE) -> None:
        self._url = url
        self._queue = queue
        self._connection: pika.BlockingConnection | None = None
        self._channel: pika.adapters.blocking_connection.BlockingChannel | None = None
        self._connect()

    def _connect(self) -> None:
        params = pika.URLParameters(self._url)
        logger.info("Connecting to RabbitMQ at %s", params.host)
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()
        self._channel.queue_declare(queue=self._queue, durable=True)
        logger.info("Queue '%s' declared (durable=True)", self._queue)

    def _reconnect(self) -> None:
        for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
            logger.warning(
                "Reconnecting to RabbitMQ (attempt %d/%d)", attempt, MAX_RECONNECT_ATTEMPTS
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

    def publish(self, event: ConflictEvent) -> None:
        body = json.dumps(asdict(event), default=_serialize_datetime)

        if self._channel is None:
            self._reconnect()

        try:
            self._channel.basic_publish(  # type: ignore[union-attr]
                exchange="",
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
            self._channel.basic_publish(  # type: ignore[union-attr]
                exchange="",
                routing_key=self._queue,
                body=body,
                properties=pika.BasicProperties(
                    delivery_mode=pika.DeliveryMode.Persistent,
                    content_type="application/json",
                ),
            )
        logger.debug("Published: %s:%s", event.source, event.source_id)

    def sleep(self, seconds: float) -> None:
        """Sleep while keeping the AMQP connection alive (processes heartbeats)."""
        if self._connection is None:
            self._reconnect()

        try:
            self._connection.sleep(seconds)  # type: ignore[union-attr]
        except (pika.exceptions.StreamLostError, pika.exceptions.AMQPConnectionError):
            logger.warning("Connection lost during sleep, reconnecting")
            self._reconnect()
            self._connection.sleep(seconds)  # type: ignore[union-attr]

    def close(self) -> None:
        if self._connection and self._connection.is_open:
            self._connection.close()
            logger.info("RabbitMQ connection closed")
