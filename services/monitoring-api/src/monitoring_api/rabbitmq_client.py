"""RabbitMQClient — reads queue and exchange info from the RabbitMQ Management HTTP API.

RabbitMQ ships with an optional Management Plugin that exposes a REST API.
We call two endpoints:
  GET /api/queues/%2F       — all queues in the default vhost ("/")
  GET /api/exchanges/%2F   — all exchanges in the default vhost

%2F is the URL-encoded form of "/", which is the default RabbitMQ vhost.

We use httpx.AsyncClient rather than the stdlib urllib because:
  1. It supports async/await natively, so calls don't block the event loop.
  2. It has a clean API for Basic Auth and JSON responses.
  3. It's already a dependency (required for FastAPI's TestClient in tests).
"""

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class QueueInfo:
    name: str
    messages: int
    consumers: int
    publish_rate: float
    deliver_rate: float


@dataclass
class ExchangeInfo:
    name: str
    type: str
    publish_rate: float


@dataclass
class BindingInfo:
    """Represents a binding between a RabbitMQ exchange and a queue.

    RabbitMQ routes messages from an exchange to a queue based on bindings.
    The topology builder uses these to draw edges from exchange nodes to queue
    nodes in the pipeline graph.

    source     — the exchange name (empty string = default exchange, usually skipped)
    destination — the queue name receiving messages from the exchange
    routing_key — the routing key pattern (empty for fanout exchanges)
    """

    source: str  # exchange name
    destination: str  # queue name
    routing_key: str


def _safe_rate(stats: dict, *keys: str) -> float:
    """Drill into a nested dict with a chain of keys, returning 0.0 if any key is absent.

    Example:
        _safe_rate(msg_stats, "publish_details", "rate")
        # returns msg_stats["publish_details"]["rate"] or 0.0

    We use this because message_stats is absent entirely when no messages have
    flowed through a queue yet — we don't want a KeyError to crash the request.
    """
    node = stats
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return 0.0
        node = node[key]
    return float(node) if node is not None else 0.0


class RabbitMQClient:
    """Reads queue and exchange metrics from the RabbitMQ Management API.

    All methods are async because they make HTTP calls. Instantiate once at
    startup and reuse the same httpx.AsyncClient across requests.

    The AsyncClient keeps a connection pool open, which is more efficient than
    opening a new TCP connection on every request.
    """

    def __init__(self, management_url: str, user: str, password: str) -> None:
        # Base URL looks like "http://rabbitmq:15672" — no trailing slash.
        self._base = management_url.rstrip("/")
        self._auth = (user, password)
        # The client is created once. In a real service you'd close it on shutdown.
        self._http = httpx.AsyncClient(auth=self._auth, timeout=5.0)

    async def get_queues(self) -> list[QueueInfo]:
        """Return stats for all queues in the default vhost.

        Returns empty list on connection failure (graceful degradation).
        """
        try:
            resp = await self._http.get(f"{self._base}/api/queues/%2F")
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("RabbitMQ queue fetch failed: %s", exc)
            return []

        results: list[QueueInfo] = []
        for q in data:
            msg_stats = q.get("message_stats", {})
            results.append(
                QueueInfo(
                    name=q["name"],
                    messages=q.get("messages", 0),
                    consumers=q.get("consumers", 0),
                    publish_rate=_safe_rate(msg_stats, "publish_details", "rate"),
                    deliver_rate=_safe_rate(msg_stats, "deliver_get_details", "rate"),
                )
            )
        return results

    async def get_exchanges(self) -> list[ExchangeInfo]:
        """Return stats for our application exchanges.

        Filters out the default exchange ('') and all built-in 'amq.*'
        exchanges that RabbitMQ creates automatically — those are internal
        plumbing, not application-level routing.
        """
        try:
            resp = await self._http.get(f"{self._base}/api/exchanges/%2F")
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("RabbitMQ exchange fetch failed: %s", exc)
            return []

        results: list[ExchangeInfo] = []
        for ex in data:
            name = ex.get("name", "")
            # Skip the default nameless exchange and all built-in amq.* exchanges.
            if not name or name.startswith("amq."):
                continue
            msg_stats = ex.get("message_stats", {})
            results.append(
                ExchangeInfo(
                    name=name,
                    type=ex.get("type", "unknown"),
                    publish_rate=_safe_rate(msg_stats, "publish_in_details", "rate"),
                )
            )
        return results

    async def get_bindings(self) -> list[BindingInfo]:
        """Return exchange-to-queue bindings in the default vhost.

        Calls GET /api/bindings/%2F which lists every binding. We filter to
        only queue destinations (destination_type == 'queue') and skip bindings
        from the nameless default exchange, since those are implicit and not
        application-level routing decisions.

        Returns empty list on connection failure (graceful degradation).
        """
        try:
            resp = await self._http.get(f"{self._base}/api/bindings/%2F")
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("RabbitMQ bindings fetch failed: %s", exc)
            return []

        results: list[BindingInfo] = []
        for b in data:
            source = b.get("source", "")
            # Skip the default (nameless) exchange — it's implicit infrastructure.
            if not source:
                continue
            # We only care about exchange→queue bindings, not exchange→exchange.
            if b.get("destination_type") != "queue":
                continue
            results.append(
                BindingInfo(
                    source=source,
                    destination=b.get("destination", ""),
                    routing_key=b.get("routing_key", ""),
                )
            )
        return results

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._http.aclose()
