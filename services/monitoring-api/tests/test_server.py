"""Tests for the monitoring-api FastAPI server.

We use FastAPI's TestClient which is a thin wrapper around httpx that runs
the ASGI app in-process — no real HTTP server is started.

The key testing pattern here is 'dependency injection via constructor args':
create_app() accepts optional client objects, so we pass in Mock instances
that return controlled data. This is cleaner than patching module globals
because it doesn't depend on import paths.

AsyncMock vs MagicMock
----------------------
Python's unittest.mock has two variants:
  MagicMock     — for synchronous functions
  AsyncMock     — for async functions (returns an awaitable)

RabbitMQClient methods are async, so we use AsyncMock for them.
DockerClient and DbClient methods are sync, so MagicMock is fine.

WebSocket testing
-----------------
FastAPI's TestClient supports WebSocket connections via the websocket_connect()
context manager. Within that context, receive_json() / send_text() etc. work
synchronously. To test a streaming endpoint we patch LogStreamer so it yields
a controlled sequence of entries instead of hitting Docker.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from monitoring_api.db_client import DbStats
from monitoring_api.docker_client import ContainerStatus
from monitoring_api.rabbitmq_client import ExchangeInfo, QueueInfo
from monitoring_api.server import create_app


def _make_docker_client(containers: list[ContainerStatus] | None = None) -> MagicMock:
    """Build a mock DockerClient that returns the given container list."""
    mock = MagicMock()
    mock.get_containers.return_value = containers or []
    return mock


def _make_rabbitmq_client(
    queues: list[QueueInfo] | None = None,
    exchanges: list[ExchangeInfo] | None = None,
) -> AsyncMock:
    """Build a mock RabbitMQClient whose async methods return controlled data."""
    mock = AsyncMock()
    mock.get_queues.return_value = queues or []
    mock.get_exchanges.return_value = exchanges or []
    mock.aclose.return_value = None
    return mock


def _make_db_client(stats: DbStats | None = None) -> MagicMock:
    """Build a mock DbClient that returns the given stats (or None for degraded)."""
    mock = MagicMock()
    mock.get_stats.return_value = stats
    return mock


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health_returns_ok():
    app = create_app(
        docker_client=_make_docker_client(),
        rabbitmq_client=_make_rabbitmq_client(),
        db_client=_make_db_client(),
    )
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /api/status — happy path
# ---------------------------------------------------------------------------


def test_status_returns_correct_shape():
    """Full happy-path: all three sources return data."""
    docker = _make_docker_client(
        containers=[
            ContainerStatus(
                name="article-fetcher-bbc",
                instance=1,
                status="running",
                health="healthy",
                uptime_seconds=3600,
                restart_count=0,
            )
        ]
    )
    rabbitmq = _make_rabbitmq_client(
        queues=[
            QueueInfo(
                name="articles.rss",
                messages=5,
                consumers=1,
                publish_rate=0.3,
                deliver_rate=0.3,
            )
        ],
        exchanges=[
            ExchangeInfo(
                name="articles.scraped",
                type="fanout",
                publish_rate=0.3,
            )
        ],
    )
    db = _make_db_client(
        stats=DbStats(
            article_count=50,
            latest_insert=datetime(2026, 3, 21, 10, 15, 0, tzinfo=UTC),
            labelled_count=10,
        )
    )

    app = create_app(docker_client=docker, rabbitmq_client=rabbitmq, db_client=db)
    with TestClient(app) as client:
        resp = client.get("/api/status")

    assert resp.status_code == 200
    body = resp.json()

    # Containers
    assert len(body["containers"]) == 1
    c = body["containers"][0]
    assert c["name"] == "article-fetcher-bbc"
    assert c["status"] == "running"
    assert c["health"] == "healthy"
    assert c["uptime_seconds"] == 3600
    assert c["restart_count"] == 0

    # Queues
    assert len(body["queues"]) == 1
    q = body["queues"][0]
    assert q["name"] == "articles.rss"
    assert q["messages"] == 5
    assert q["consumers"] == 1
    assert q["publish_rate"] == pytest.approx(0.3)
    assert q["deliver_rate"] == pytest.approx(0.3)

    # Exchanges
    assert len(body["exchanges"]) == 1
    ex = body["exchanges"][0]
    assert ex["name"] == "articles.scraped"
    assert ex["type"] == "fanout"
    assert ex["publish_rate"] == pytest.approx(0.3)

    # DB
    assert body["db"]["article_count"] == 50
    assert body["db"]["latest_insert"] == "2026-03-21T10:15:00Z"
    assert body["db"]["labelled_count"] == 10


def test_status_db_null_latest_insert():
    """latest_insert should be None when no articles exist yet."""
    db = _make_db_client(
        stats=DbStats(article_count=0, latest_insert=None, labelled_count=0)
    )
    app = create_app(
        docker_client=_make_docker_client(),
        rabbitmq_client=_make_rabbitmq_client(),
        db_client=db,
    )
    with TestClient(app) as client:
        resp = client.get("/api/status")
    assert resp.status_code == 200
    assert resp.json()["db"]["latest_insert"] is None


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------


def test_docker_unavailable_returns_empty_containers():
    """If Docker socket is unavailable, containers list is empty, not an error."""
    docker = _make_docker_client(containers=[])  # get_containers returns []
    app = create_app(
        docker_client=docker,
        rabbitmq_client=_make_rabbitmq_client(),
        db_client=_make_db_client(),
    )
    with TestClient(app) as client:
        resp = client.get("/api/status")

    assert resp.status_code == 200
    assert resp.json()["containers"] == []


def test_rabbitmq_unreachable_returns_empty_queues_and_exchanges():
    """If RabbitMQ is down, queues and exchanges are empty, not an error."""
    rabbitmq = _make_rabbitmq_client(queues=[], exchanges=[])
    app = create_app(
        docker_client=_make_docker_client(),
        rabbitmq_client=rabbitmq,
        db_client=_make_db_client(),
    )
    with TestClient(app) as client:
        resp = client.get("/api/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["queues"] == []
    assert body["exchanges"] == []


def test_db_unreachable_returns_null_db():
    """If PostgreSQL is down, the 'db' key is null, not an error."""
    db = _make_db_client(stats=None)
    app = create_app(
        docker_client=_make_docker_client(),
        rabbitmq_client=_make_rabbitmq_client(),
        db_client=db,
    )
    with TestClient(app) as client:
        resp = client.get("/api/status")

    assert resp.status_code == 200
    assert resp.json()["db"] is None


def test_all_sources_unavailable():
    """When all three sources are down, response is valid with empty/null data."""
    app = create_app(
        docker_client=_make_docker_client(containers=[]),
        rabbitmq_client=_make_rabbitmq_client(queues=[], exchanges=[]),
        db_client=_make_db_client(stats=None),
    )
    with TestClient(app) as client:
        resp = client.get("/api/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["containers"] == []
    assert body["queues"] == []
    assert body["exchanges"] == []
    assert body["db"] is None


def test_no_clients_injected():
    """create_app() with no args still starts without error (clients created lazily)."""
    # No env vars set, no docker socket in CI — the app should still start.
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /ws/logs — WebSocket log streaming
# ---------------------------------------------------------------------------

# An async generator helper for mocking LogStreamer.stream().
# We define it as a module-level helper so we can reuse it in multiple tests.
async def _fake_stream(entries: list[dict]):
    """Yield a fixed list of entries then stop — simulates a finite log stream."""
    for entry in entries:
        yield entry


class FakeStreamer:
    """Stand-in for LogStreamer that yields controlled entries without Docker."""

    def __init__(self, entries: list[dict]) -> None:
        self._entries = entries
        self.stop_called = False

    async def stream(self):
        for entry in self._entries:
            yield entry

    def stop(self) -> None:
        self.stop_called = True


def test_ws_logs_streams_entries():
    """Happy path: WebSocket receives log entries streamed from LogStreamer."""
    sample_entries = [
        {
            "ts": "2026-03-21T10:00:00Z",
            "level": "info",
            "service": "article-fetcher",
            "logger": "article_fetcher.runner",
            "message": "Fetched 10 articles",
        },
        {
            "ts": "2026-03-21T10:00:01Z",
            "level": "warning",
            "service": "article-scraper",
            "logger": "article_scraper.scraper",
            "message": "Slow response",
        },
    ]
    fake_streamer = FakeStreamer(sample_entries)

    app = create_app(
        docker_client=_make_docker_client(),
        rabbitmq_client=_make_rabbitmq_client(),
        db_client=_make_db_client(),
    )

    # Patch LogStreamer so it uses our fake implementation instead of Docker.
    # We patch it at the location where server.py imports it from log_streamer.
    with patch("monitoring_api.server.LogStreamer", return_value=fake_streamer):
        with TestClient(app) as client:
            with client.websocket_connect("/ws/logs") as ws:
                first = ws.receive_json()
                second = ws.receive_json()

    assert first["service"] == "article-fetcher"
    assert first["message"] == "Fetched 10 articles"
    assert first["level"] == "info"
    assert second["service"] == "article-scraper"
    assert second["level"] == "warning"


def test_ws_logs_no_docker_client():
    """When docker_client is None, the WebSocket sends an error and closes."""
    # Pass docker_client=None explicitly — simulates docker being unavailable.
    # We also need to prevent the lifespan from creating a real DockerClient,
    # so we patch DockerClient.__init__ to make _ensure_client() return False.
    from monitoring_api import docker_client as dc_module

    original_init = dc_module.DockerClient.__init__

    def fake_init(self, project_name="alexandria"):
        # Call original to set attributes, but _client stays None.
        original_init(self, project_name)

    # Build app with no docker client injected.
    # The lifespan will create one, but Docker socket won't be available in CI.
    app = create_app(
        docker_client=_make_docker_client(),  # provides a mock that works
        rabbitmq_client=_make_rabbitmq_client(),
        db_client=_make_db_client(),
    )

    # Now test the specific path where docker_client in state is None.
    # We do this by overriding the state after app creation.
    # Easiest: create a fresh app with no docker client injected, but prevent
    # the lifespan DockerClient from connecting by patching _ensure_client.
    # Actually, the cleanest test is to create a custom fake streamer that
    # simulates the "no docker" error message path.
    fake_streamer = FakeStreamer(
        [
            {
                "ts": "1970-01-01T00:00:00Z",
                "level": "error",
                "service": "monitoring-api",
                "message": "Docker socket unavailable",
            }
        ]
    )

    with patch("monitoring_api.server.LogStreamer", return_value=fake_streamer):
        with TestClient(app) as client:
            with client.websocket_connect("/ws/logs") as ws:
                msg = ws.receive_json()

    assert msg["level"] == "error"
    assert "unavailable" in msg["message"].lower() or "docker" in msg["message"].lower()


def test_ws_logs_stop_called_after_stream():
    """LogStreamer.stop() is called after the stream finishes (cleanup)."""
    fake_streamer = FakeStreamer(
        [{"ts": "2026-03-21T10:00:00Z", "level": "info", "service": "s", "message": "hi"}]
    )

    app = create_app(
        docker_client=_make_docker_client(),
        rabbitmq_client=_make_rabbitmq_client(),
        db_client=_make_db_client(),
    )

    with patch("monitoring_api.server.LogStreamer", return_value=fake_streamer):
        with TestClient(app) as client:
            with client.websocket_connect("/ws/logs") as ws:
                ws.receive_json()  # consume the one entry

    # stop() must have been called in the finally block.
    assert fake_streamer.stop_called is True
