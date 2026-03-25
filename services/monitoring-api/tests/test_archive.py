"""Tests for the archive endpoints: GET /api/archive/articles and reparse.

Follows the same injection pattern as test_labelling.py and test_dashboard.py:
mock ArticleClient is passed to create_app(), and pika is patched at the
module level so no real RabbitMQ connection is attempted.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from monitoring_api.article_client import ArticleDetail
from monitoring_api.server import create_app


def _make_mocks(article_mock: MagicMock | None = None) -> dict:
    """Build a minimal set of mocks for create_app."""
    docker = MagicMock()
    docker.get_containers.return_value = []

    rabbitmq = AsyncMock()
    rabbitmq.get_queues.return_value = []
    rabbitmq.get_exchanges.return_value = []
    rabbitmq.aclose.return_value = None

    db = MagicMock()
    db.get_stats.return_value = None

    label_mock = MagicMock()
    label_mock.get_labels.return_value = []

    return {
        "docker_client": docker,
        "rabbitmq_client": rabbitmq,
        "db_client": db,
        "article_client": article_mock or MagicMock(),
        "label_client": label_mock,
    }


def _build_app(article_mock: MagicMock) -> TestClient:
    mocks = _make_mocks(article_mock)
    app = create_app(**mocks)
    return TestClient(app)


def _sample_detail() -> ArticleDetail:
    """A fully-populated ArticleDetail for use in reparse tests."""
    return ArticleDetail(
        id=42,
        url="https://bbc.com/news/42",
        source="bbc",
        origin="bbc",
        title="Test Article",
        summary="A summary",
        content="Full content body.",
        published_at="2026-03-21T10:00:00+00:00",
        created_at="2026-03-21T10:05:00+00:00",
        fetched_at="2026-03-21T10:03:00+00:00",
        scraped_at="2026-03-21T10:04:00+00:00",
        manual_labels=None,
        automatic_labels=["CONFLICT"],
        entities=None,
    )


def _make_pika_mock() -> MagicMock:
    """Build a mock that stands in for pika.BlockingConnection.

    The channel returned by connection.channel() needs to expose
    queue_declare() and basic_publish() — we use MagicMock's attribute
    auto-creation, which returns a new MagicMock for any attribute access,
    so those calls just succeed silently without any explicit setup.
    """
    connection = MagicMock()
    # connection.channel() returns a mock channel automatically.
    return connection


# ---------------------------------------------------------------------------
# POST /api/archive/articles/{article_id}/reparse — happy path
# ---------------------------------------------------------------------------


def test_reparse_returns_queued_status():
    """Happy path: article is found, deleted, and published; returns queued status."""
    mock = MagicMock()
    mock.get_article_detail.return_value = _sample_detail()
    mock.delete_article.return_value = True

    with patch("monitoring_api.server.pika.BlockingConnection", return_value=_make_pika_mock()):
        with _build_app(mock) as client:
            resp = client.post("/api/archive/articles/42/reparse")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "queued"
    assert body["url"] == "https://bbc.com/news/42"


def test_reparse_calls_get_article_detail_with_correct_id():
    """The reparse endpoint passes the correct article_id to get_article_detail."""
    mock = MagicMock()
    mock.get_article_detail.return_value = _sample_detail()
    mock.delete_article.return_value = True

    with patch("monitoring_api.server.pika.BlockingConnection", return_value=_make_pika_mock()):
        with _build_app(mock) as client:
            client.post("/api/archive/articles/42/reparse")

    mock.get_article_detail.assert_called_once_with(42)


def test_reparse_calls_delete_article_with_correct_id():
    """The reparse endpoint deletes the article by the same id it fetched."""
    mock = MagicMock()
    mock.get_article_detail.return_value = _sample_detail()
    mock.delete_article.return_value = True

    with patch("monitoring_api.server.pika.BlockingConnection", return_value=_make_pika_mock()):
        with _build_app(mock) as client:
            client.post("/api/archive/articles/42/reparse")

    mock.delete_article.assert_called_once_with(42)


def test_reparse_publishes_correct_message_fields():
    """The message published to RabbitMQ contains the seven expected fields."""
    mock = MagicMock()
    detail = _sample_detail()
    mock.get_article_detail.return_value = detail
    mock.delete_article.return_value = True

    connection_mock = _make_pika_mock()
    channel_mock = connection_mock.channel.return_value

    with patch("monitoring_api.server.pika.BlockingConnection", return_value=connection_mock):
        with _build_app(mock) as client:
            client.post("/api/archive/articles/42/reparse")

    # basic_publish should have been called once
    assert channel_mock.basic_publish.call_count == 1
    call_kwargs = channel_mock.basic_publish.call_args.kwargs

    # Decode the body to check its contents
    body = json.loads(call_kwargs["body"])
    assert body["source"] == detail.source
    assert body["origin"] == detail.origin
    assert body["title"] == detail.title
    assert body["url"] == detail.url
    assert body["summary"] == detail.summary
    assert body["published"] == detail.published_at
    assert "fetched_at" in body  # timestamp generated at call time; just check key exists

    # Routing key must be the articles.rss queue
    assert call_kwargs["routing_key"] == "articles.rss"


def test_reparse_summary_none_becomes_empty_string():
    """When summary is None, the published message contains an empty string."""
    detail = _sample_detail()
    detail.summary = None

    mock = MagicMock()
    mock.get_article_detail.return_value = detail
    mock.delete_article.return_value = True

    connection_mock = _make_pika_mock()
    channel_mock = connection_mock.channel.return_value

    with patch("monitoring_api.server.pika.BlockingConnection", return_value=connection_mock):
        with _build_app(mock) as client:
            client.post("/api/archive/articles/42/reparse")

    body = json.loads(channel_mock.basic_publish.call_args.kwargs["body"])
    assert body["summary"] == ""


# ---------------------------------------------------------------------------
# POST /api/archive/articles/{article_id}/reparse — error paths
# ---------------------------------------------------------------------------


def test_reparse_article_not_found_returns_404():
    """When get_article_detail returns None, endpoint returns 404."""
    mock = MagicMock()
    mock.get_article_detail.return_value = None

    with patch("monitoring_api.server.pika.BlockingConnection", return_value=_make_pika_mock()):
        with _build_app(mock) as client:
            resp = client.post("/api/archive/articles/999/reparse")

    assert resp.status_code == 404
    assert "not found" in resp.json()["error"].lower()


def test_reparse_no_article_client_returns_503():
    """When ArticleClient is not wired up, endpoint returns 503."""
    mocks = _make_mocks(article_mock=None)
    mocks["article_client"] = None
    app = create_app(**mocks)

    with TestClient(app) as client:
        resp = client.post("/api/archive/articles/1/reparse")

    assert resp.status_code == 503
    assert resp.json()["error"] == "unavailable"


def test_reparse_pika_connection_failure_returns_502():
    """When pika raises (RabbitMQ unreachable), endpoint returns 502."""
    mock = MagicMock()
    mock.get_article_detail.return_value = _sample_detail()
    mock.delete_article.return_value = True

    with patch(
        "monitoring_api.server.pika.BlockingConnection",
        side_effect=Exception("Connection refused"),
    ):
        with _build_app(mock) as client:
            resp = client.post("/api/archive/articles/42/reparse")

    assert resp.status_code == 502
    assert "reparse" in resp.json()["error"].lower()


def test_reparse_delete_not_called_when_article_not_found():
    """delete_article must NOT be called if get_article_detail returned None."""
    mock = MagicMock()
    mock.get_article_detail.return_value = None

    with patch("monitoring_api.server.pika.BlockingConnection", return_value=_make_pika_mock()):
        with _build_app(mock) as client:
            client.post("/api/archive/articles/999/reparse")

    mock.delete_article.assert_not_called()
