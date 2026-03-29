"""Tests for GET /api/dashboard/articles.

Follows the same patterns as test_labelling.py: inject a mock ArticleClient
via create_app(article_client=mock) and test with FastAPI's TestClient.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from monitoring_api.article_client import DashboardArticle
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


def _sample_articles() -> list[DashboardArticle]:
    return [
        DashboardArticle(
            id=1,
            url="https://bbc.com/news/1",
            source="bbc",
            origin="bbc",
            title="Iran launches strikes",
            summary="A brief summary",
            published_at="2026-03-21T10:00:00+00:00",
            created_at="2026-03-21T10:05:00+00:00",
            manual_labels=None,
            automatic_labels=["CONFLICT"],
            entities=[
                {
                    "text": "Iran",
                    "label": "GPE",
                    "wikidata_id": "Q794",
                    "canonical_name": "Iran",
                    "description": "country in Western Asia",
                    "latitude": 32.0,
                    "longitude": 53.0,
                }
            ],
        ),
        DashboardArticle(
            id=2,
            url="https://reuters.com/world/2",
            source="reuters",
            origin="reuters",
            title="EU summit on trade",
            summary=None,
            published_at=None,
            created_at="2026-03-20T09:00:00+00:00",
            manual_labels=["POLITICS"],
            automatic_labels=None,
            entities=None,
        ),
    ]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_dashboard_articles_returns_correct_shape():
    """Happy path: endpoint returns a list of articles with all expected fields."""
    mock = MagicMock()
    mock.get_dashboard_articles.return_value = _sample_articles()

    with _build_app(mock) as client:
        resp = client.get("/api/dashboard/articles")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 2

    first = body[0]
    assert first["id"] == 1
    assert first["url"] == "https://bbc.com/news/1"
    assert first["source"] == "bbc"
    assert first["origin"] == "bbc"
    assert first["title"] == "Iran launches strikes"
    assert first["summary"] == "A brief summary"
    assert first["published_at"] == "2026-03-21T10:00:00+00:00"
    assert first["created_at"] == "2026-03-21T10:05:00+00:00"
    assert first["manual_labels"] is None
    assert first["automatic_labels"] == ["CONFLICT"]
    assert len(first["entities"]) == 1
    assert first["entities"][0]["wikidata_id"] == "Q794"
    assert first["entities"][0]["latitude"] == 32.0
    assert first["entities"][0]["longitude"] == 53.0


def test_dashboard_articles_null_entities_and_labels():
    """Articles with null entities and labels are serialised correctly."""
    mock = MagicMock()
    mock.get_dashboard_articles.return_value = _sample_articles()

    with _build_app(mock) as client:
        resp = client.get("/api/dashboard/articles")

    body = resp.json()
    second = body[1]
    assert second["entities"] is None
    assert second["published_at"] is None
    assert second["automatic_labels"] is None
    assert second["manual_labels"] == ["POLITICS"]


def test_dashboard_articles_default_since_is_24h_ago():
    """When no `since` is provided, the client is called with a timestamp ~24 h ago."""
    mock = MagicMock()
    mock.get_dashboard_articles.return_value = []

    before = datetime.now(timezone.utc)
    with _build_app(mock) as client:
        client.get("/api/dashboard/articles")
    after = datetime.now(timezone.utc)

    called_since = mock.get_dashboard_articles.call_args[0][0]
    # The value must be a valid ISO timestamp string.
    assert isinstance(called_since, str)
    # Parse it back and verify it falls in the expected 24-hour window.
    parsed = datetime.fromisoformat(called_since)
    assert before - timedelta(hours=24, seconds=1) <= parsed <= after - timedelta(hours=23, minutes=59)


def test_dashboard_articles_custom_since_is_forwarded():
    """An explicit `since` query param is forwarded directly to the client."""
    mock = MagicMock()
    mock.get_dashboard_articles.return_value = []

    with _build_app(mock) as client:
        client.get("/api/dashboard/articles?since=2024-01-15T00:00:00Z")

    mock.get_dashboard_articles.assert_called_once_with("2024-01-15T00:00:00Z")


def test_dashboard_articles_since_filters_by_timestamp():
    """When `since` is provided, only articles after that timestamp are returned."""
    mock = MagicMock()
    # Return only the first article (published after the since timestamp).
    mock.get_dashboard_articles.return_value = _sample_articles()[:1]

    with _build_app(mock) as client:
        resp = client.get("/api/dashboard/articles?since=2026-03-21T00:00:00Z")

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    mock.get_dashboard_articles.assert_called_once_with("2026-03-21T00:00:00Z")


def test_dashboard_articles_empty_list():
    """When there are no articles, the endpoint returns an empty list."""
    mock = MagicMock()
    mock.get_dashboard_articles.return_value = []

    with _build_app(mock) as client:
        resp = client.get("/api/dashboard/articles")

    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Error / unavailability cases
# ---------------------------------------------------------------------------


def test_dashboard_articles_client_returns_none_gives_503():
    """When get_dashboard_articles returns None (DB error), endpoint returns 503."""
    mock = MagicMock()
    mock.get_dashboard_articles.return_value = None

    with _build_app(mock) as client:
        resp = client.get("/api/dashboard/articles")

    assert resp.status_code == 503
    assert resp.json()["error"] == "unavailable"


def test_dashboard_articles_no_article_client_gives_503():
    """When no ArticleClient is wired up, endpoint returns 503."""
    mocks = _make_mocks(article_mock=None)
    # Explicitly set article_client to None so state["articles"] is None
    mocks["article_client"] = None
    app = create_app(**mocks)

    with TestClient(app) as client:
        resp = client.get("/api/dashboard/articles")

    assert resp.status_code == 503
    assert resp.json()["error"] == "unavailable"
