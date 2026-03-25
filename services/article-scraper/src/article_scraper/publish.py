"""Publish scraped articles to a RabbitMQ fanout exchange."""

import json
import logging
import time
from dataclasses import asdict

import pika
import pika.exceptions

from article_scraper.models import ScrapedArticle

logger = logging.getLogger(__name__)

DEFAULT_EXCHANGE = "articles.scraped"
QUEUE_RAW = "articles.raw"
QUEUE_TRAINING = "articles.training"

MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY_SECONDS = 5


class RabbitMqPublisher:
    """Publishes ScrapedArticle objects to a RabbitMQ fanout exchange as JSON.

    A fanout exchange delivers every message to all bound queues, ignoring the
    routing key entirely. Two queues are bound at startup: one for downstream
    consumers of raw articles and one for ML training pipelines.

    Uses a connect-per-publish pattern: opens a connection, publishes, then
    closes. This avoids idle-connection heartbeat timeouts — pika's
    BlockingConnection can't service heartbeats while the main thread is busy
    scraping articles over HTTP. The overhead of reconnecting per article is
    negligible compared to the scraping time itself.
    """

    def __init__(self, url: str, exchange: str = DEFAULT_EXCHANGE) -> None:
        self._url = url
        self._exchange = exchange

    def _connect(
        self,
    ) -> tuple[
        pika.BlockingConnection,
        pika.adapters.blocking_connection.BlockingChannel,
    ]:
        """Open a fresh connection, declare exchange and bind queues.

        If exchange/queue declaration fails (e.g. exchange already exists
        with different parameters), the connection is closed before the
        exception propagates — prevents leaked connections.
        """
        params = pika.URLParameters(self._url)
        connection = pika.BlockingConnection(params)
        try:
            channel = connection.channel()

            channel.exchange_declare(
                exchange=self._exchange,
                exchange_type="fanout",
                durable=True,
            )

            for queue_name in (QUEUE_RAW, QUEUE_TRAINING):
                channel.queue_declare(queue=queue_name, durable=True)
                channel.queue_bind(queue=queue_name, exchange=self._exchange)

            return connection, channel
        except Exception:
            connection.close()
            raise

    def publish(self, article: ScrapedArticle) -> None:
        """Serialize a ScrapedArticle to JSON and publish it to the fanout exchange.

        Opens a fresh connection, publishes, and closes. Retries with backoff
        if the broker is temporarily unreachable.
        """
        body = json.dumps(asdict(article))

        for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
            try:
                connection, channel = self._connect()
                try:
                    channel.basic_publish(
                        exchange=self._exchange,
                        routing_key="",
                        body=body,
                        properties=pika.BasicProperties(
                            delivery_mode=pika.DeliveryMode.Persistent,
                            content_type="application/json",
                        ),
                    )
                    logger.debug("Published: %s", article.url)
                    return
                finally:
                    connection.close()
            except pika.exceptions.AMQPConnectionError:
                if attempt < MAX_RECONNECT_ATTEMPTS:
                    logger.warning(
                        "Publish attempt %d/%d failed, retrying in %ds",
                        attempt,
                        MAX_RECONNECT_ATTEMPTS,
                        RECONNECT_DELAY_SECONDS,
                    )
                    time.sleep(RECONNECT_DELAY_SECONDS)
                else:
                    logger.error("Failed to publish after %d attempts", MAX_RECONNECT_ATTEMPTS)
                    raise
