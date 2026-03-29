"""Tests for the labelling endpoints in the monitoring-api.

Follows the same patterns as test_server.py: we inject a mock ArticleClient
via create_app(article_client=mock) and test with FastAPI's TestClient.

ArticleClient methods are synchronous, so we use MagicMock (not AsyncMock).
The server wraps them in run_in_executor, but TestClient handles the async
event loop internally — we don't need to worry about that in tests.
"""

import json
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from monitoring_api.article_client import (
    ArticlePage,
    ArticleSummary,
    LabellingStats,
)
from monitoring_api.label_client import ClassificationLabel
from monitoring_api.server import create_app

# The default set of labels returned by the mock ClassificationLabelClient.
# Mirrors the seed data in schema.py so existing tests continue to work.
_DEFAULT_LABELS = [
    ClassificationLabel(id=i, name=name, description="", color="", enabled=True, created_at="")
    for i, name in enumerate(
        ["CONFLICT", "ENVIRONMENT", "FINANCIAL", "HEALTH", "POLITICS", "TECHNOLOGY"], start=1
    )
]


def _make_mocks(
    article_mock: MagicMock | None = None,
    label_mock: MagicMock | None = None,
) -> dict:
    """Build a minimal set of mocks for create_app.

    We need docker, rabbitmq, and db mocks even though we're testing labelling,
    because create_app requires them to avoid hitting real services.
    """
    docker = MagicMock()
    docker.get_containers.return_value = []

    rabbitmq = AsyncMock()
    rabbitmq.get_queues.return_value = []
    rabbitmq.get_exchanges.return_value = []
    rabbitmq.aclose.return_value = None

    db = MagicMock()
    db.get_stats.return_value = None

    if label_mock is None:
        label_mock = MagicMock()
        label_mock.get_labels.return_value = _DEFAULT_LABELS

    return {
        "docker_client": docker,
        "rabbitmq_client": rabbitmq,
        "db_client": db,
        "article_client": article_mock or MagicMock(),
        "label_client": label_mock,
    }


def _build_app(article_mock: MagicMock) -> TestClient:
    """Create the FastAPI app with a mock ArticleClient and return a TestClient."""
    mocks = _make_mocks(article_mock)
    app = create_app(**mocks)
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/labelling/stats
# ---------------------------------------------------------------------------


def test_stats_returns_correct_shape():
    """Happy path: stats endpoint returns all four fields."""
    mock = MagicMock()
    mock.get_labelling_stats.return_value = LabellingStats(
        total_count=100,
        labelled_count=25,
        unlabelled_count=75,
        progress_percent=25.0,
        classified_count=10,
    )

    with _build_app(mock) as client:
        resp = client.get("/api/labelling/stats")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 100
    assert body["labelled_count"] == 25
    assert body["unlabelled_count"] == 75
    assert body["progress_percent"] == 25.0


def test_stats_unavailable_returns_error():
    """When get_labelling_stats returns None, the endpoint returns 503."""
    mock = MagicMock()
    mock.get_labelling_stats.return_value = None

    with _build_app(mock) as client:
        resp = client.get("/api/labelling/stats")

    assert resp.status_code == 503
    assert resp.json()["error"] == "unavailable"


# ---------------------------------------------------------------------------
# GET /api/labelling/articles
# ---------------------------------------------------------------------------


def _sample_article_page() -> ArticlePage:
    """Build a sample ArticlePage for use in tests."""
    return ArticlePage(
        articles=[
            ArticleSummary(
                id=1,
                origin="bbc",
                title="Test Article",
                created_at="2026-03-21T10:00:00",
                manual_labels=None,
                automatic_labels=None,
            ),
            ArticleSummary(
                id=2,
                origin="reuters",
                title="Another Article",
                created_at="2026-03-21T11:00:00",
                manual_labels=["CONFLICT", "POLITICS"],
                automatic_labels=["POLITICS"],
            ),
        ],
        total=2,
        page=1,
        page_size=50,
    )


def test_articles_default_pagination():
    """Articles endpoint with default parameters returns correct shape."""
    mock = MagicMock()
    mock.get_articles.return_value = _sample_article_page()

    with _build_app(mock) as client:
        resp = client.get("/api/labelling/articles")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 50
    assert len(body["articles"]) == 2
    assert body["articles"][0]["title"] == "Test Article"
    assert body["articles"][1]["manual_labels"] == ["CONFLICT", "POLITICS"]

    # Verify the mock was called with default parameters (page_size default is 10)
    mock.get_articles.assert_called_once_with(1, 10, "all", "date_ingested", "desc")


def test_articles_with_filter_parameter():
    """Filter parameter is passed through to the client."""
    mock = MagicMock()
    mock.get_articles.return_value = ArticlePage(articles=[], total=0, page=1, page_size=50)

    with _build_app(mock) as client:
        resp = client.get("/api/labelling/articles?filter=unlabelled")

    assert resp.status_code == 200
    mock.get_articles.assert_called_once_with(1, 10, "unlabelled", "date_ingested", "desc")


def test_articles_with_sort_parameter():
    """Sort parameters are passed through to the client."""
    mock = MagicMock()
    mock.get_articles.return_value = ArticlePage(articles=[], total=0, page=1, page_size=50)

    with _build_app(mock) as client:
        resp = client.get("/api/labelling/articles?sort_by=source_origin&sort_dir=asc")

    assert resp.status_code == 200
    mock.get_articles.assert_called_once_with(1, 10, "all", "source_origin", "asc")


def test_articles_invalid_filter_returns_422():
    """An invalid filter value returns 422."""
    mock = MagicMock()

    with _build_app(mock) as client:
        resp = client.get("/api/labelling/articles?filter=bogus")

    assert resp.status_code == 422
    assert "Invalid filter" in resp.json()["error"]


def test_articles_invalid_sort_by_returns_422():
    """An invalid sort_by value returns 422."""
    mock = MagicMock()

    with _build_app(mock) as client:
        resp = client.get("/api/labelling/articles?sort_by=bogus")

    assert resp.status_code == 422
    assert "Invalid sort_by" in resp.json()["error"]


def test_articles_invalid_sort_dir_returns_422():
    """An invalid sort_dir value returns 422."""
    mock = MagicMock()

    with _build_app(mock) as client:
        resp = client.get("/api/labelling/articles?sort_dir=upward")

    assert resp.status_code == 422
    assert "Invalid sort_dir" in resp.json()["error"]


# ---------------------------------------------------------------------------
# PATCH /api/labelling/articles/{article_id}/labels
# ---------------------------------------------------------------------------


def test_update_labels_success():
    """Happy path: valid labels are applied and the endpoint returns ok."""
    mock = MagicMock()
    mock.update_labels.return_value = True

    with _build_app(mock) as client:
        resp = client.patch(
            "/api/labelling/articles/42/labels",
            json={"labels": ["CONFLICT", "POLITICS"]},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["article_id"] == 42
    assert body["labels"] == ["CONFLICT", "POLITICS"]
    mock.update_labels.assert_called_once_with(42, ["CONFLICT", "POLITICS"])


def test_update_labels_invalid_label_name_returns_422():
    """An invalid label name returns 422 with a descriptive error."""
    mock = MagicMock()

    with _build_app(mock) as client:
        resp = client.patch(
            "/api/labelling/articles/1/labels",
            json={"labels": ["CONFLICT", "INVALID_LABEL"]},
        )

    assert resp.status_code == 422
    body = resp.json()
    assert "Invalid label" in body["error"]
    assert "INVALID_LABEL" in body["error"]


def test_update_labels_too_many_returns_422():
    """More than MAX_LABELS labels returns 422."""
    mock = MagicMock()

    with _build_app(mock) as client:
        resp = client.patch(
            "/api/labelling/articles/1/labels",
            json={"labels": ["CONFLICT", "POLITICS", "FINANCIAL", "HEALTH"]},
        )

    assert resp.status_code == 422
    body = resp.json()
    assert "Too many labels" in body["error"]


def test_update_labels_clears_when_empty_list():
    """An empty labels list clears the labels (sets to NULL in DB)."""
    mock = MagicMock()
    mock.update_labels.return_value = True

    with _build_app(mock) as client:
        resp = client.patch(
            "/api/labelling/articles/42/labels",
            json={"labels": []},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["labels"] == []
    mock.update_labels.assert_called_once_with(42, [])


def test_update_labels_not_found_returns_404():
    """When update_labels returns False (no matching row), endpoint returns 404."""
    mock = MagicMock()
    mock.update_labels.return_value = False

    with _build_app(mock) as client:
        resp = client.patch(
            "/api/labelling/articles/999/labels",
            json={"labels": ["CONFLICT"]},
        )

    assert resp.status_code == 404
    assert "not found" in resp.json()["error"].lower()


# ---------------------------------------------------------------------------
# GET /api/labelling/export
# ---------------------------------------------------------------------------


def test_export_returns_jsonl_content_type():
    """Export endpoint returns NDJSON with correct content type and headers."""
    mock = MagicMock()
    mock.get_unlabelled_jsonl.return_value = [
        {
            "id": 1,
            "origin": "bbc",
            "title": "Test",
            "summary": "A summary",
            "content": "Full content",
            "published_at": "2026-03-21T10:00:00",
            "created_at": "2026-03-21T10:05:00",
        },
        {
            "id": 2,
            "origin": "reuters",
            "title": "Another",
            "summary": None,
            "content": "More content",
            "published_at": "2026-03-21T11:00:00",
            "created_at": "2026-03-21T11:05:00",
        },
    ]

    with _build_app(mock) as client:
        resp = client.get("/api/labelling/export")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/x-ndjson"
    assert "unlabelled_articles.jsonl" in resp.headers["content-disposition"]

    # Each line should be valid JSON
    lines = resp.text.strip().split("\n")
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["id"] == 1
    assert first["origin"] == "bbc"
    second = json.loads(lines[1])
    assert second["id"] == 2


def test_export_empty_returns_empty_body():
    """Export with no unlabelled articles returns an empty body."""
    mock = MagicMock()
    mock.get_unlabelled_jsonl.return_value = []

    with _build_app(mock) as client:
        resp = client.get("/api/labelling/export")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/x-ndjson"
    assert resp.text == ""
