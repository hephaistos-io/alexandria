"""Tests for the classification label CRUD endpoints.

Follows the same pattern as test_labelling.py: inject a mock
ClassificationLabelClient via create_app(label_client=mock) and test
with FastAPI's TestClient.
"""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from monitoring_api.label_client import ClassificationLabel
from monitoring_api.server import create_app


def _make_mocks(
    label_mock: MagicMock | None = None,
) -> dict:
    """Build a minimal set of mocks for create_app."""
    docker = MagicMock()
    docker.get_containers.return_value = []

    rabbitmq = AsyncMock()
    rabbitmq.get_queues.return_value = []
    rabbitmq.get_exchanges.return_value = []
    rabbitmq.aclose.return_value = None

    db = MagicMock()
    db.get_stats.return_value = None

    article = MagicMock()

    return {
        "docker_client": docker,
        "rabbitmq_client": rabbitmq,
        "db_client": db,
        "article_client": article,
        "label_client": label_mock or MagicMock(),
    }


def _build_app(label_mock: MagicMock) -> TestClient:
    mocks = _make_mocks(label_mock)
    app = create_app(**mocks)
    return TestClient(app)


def _sample_label(label_id: int = 1, name: str = "CONFLICT") -> ClassificationLabel:
    return ClassificationLabel(
        id=label_id,
        name=name,
        description="Armed conflicts and wars",
        color="#ffb4ab",
        enabled=True,
        created_at="2026-03-21T10:00:00",
    )


# ---------------------------------------------------------------------------
# GET /api/classification/labels
# ---------------------------------------------------------------------------


def test_list_labels_returns_all():
    """Happy path: GET returns a list of label dicts."""
    mock = MagicMock()
    mock.get_labels.return_value = [
        _sample_label(1, "CONFLICT"),
        _sample_label(2, "POLITICS"),
    ]

    with _build_app(mock) as client:
        resp = client.get("/api/classification/labels")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["name"] == "CONFLICT"
    assert body[1]["name"] == "POLITICS"
    assert body[0]["color"] == "#ffb4ab"
    assert body[0]["enabled"] is True


def test_list_labels_db_unavailable_returns_503():
    """When get_labels returns None the endpoint returns 503."""
    mock = MagicMock()
    mock.get_labels.return_value = None

    with _build_app(mock) as client:
        resp = client.get("/api/classification/labels")

    assert resp.status_code == 503
    assert resp.json()["error"] == "unavailable"


def test_list_labels_empty_returns_empty_list():
    """When there are no labels in the DB an empty list is returned."""
    mock = MagicMock()
    mock.get_labels.return_value = []

    with _build_app(mock) as client:
        resp = client.get("/api/classification/labels")

    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# POST /api/classification/labels
# ---------------------------------------------------------------------------


def test_create_label_success():
    """Happy path: valid body creates a label and returns it."""
    mock = MagicMock()
    mock.create_label.return_value = _sample_label(7, "ENVIRONMENT")

    with _build_app(mock) as client:
        resp = client.post(
            "/api/classification/labels",
            json={
                "name": "ENVIRONMENT",
                "description": "Climate and ecological events",
                "color": "#a3e635",
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 7
    assert body["name"] == "ENVIRONMENT"
    mock.create_label.assert_called_once_with(
        "ENVIRONMENT", "Climate and ecological events", "#a3e635"
    )


def test_create_label_default_color():
    """Color defaults to '#76A9FA' if not provided."""
    mock = MagicMock()
    mock.create_label.return_value = _sample_label(8, "NEW_LABEL")

    with _build_app(mock) as client:
        resp = client.post(
            "/api/classification/labels",
            json={"name": "NEW_LABEL", "description": "A new label"},
        )

    assert resp.status_code == 200
    # Default color was passed to the client
    mock.create_label.assert_called_once_with("NEW_LABEL", "A new label", "#76A9FA")


def test_create_label_duplicate_returns_409():
    """When create_label returns None (e.g. duplicate name), endpoint returns 409."""
    mock = MagicMock()
    mock.create_label.return_value = None

    with _build_app(mock) as client:
        resp = client.post(
            "/api/classification/labels",
            json={"name": "CONFLICT", "description": "Duplicate", "color": "#000"},
        )

    assert resp.status_code == 409
    assert "CONFLICT" in resp.json()["error"]


def test_create_label_missing_required_fields_returns_422():
    """Missing name or description returns 422 from Pydantic validation."""
    mock = MagicMock()

    with _build_app(mock) as client:
        resp = client.post("/api/classification/labels", json={"name": "ONLY_NAME"})

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/classification/labels/{id}
# ---------------------------------------------------------------------------


def test_update_label_success():
    """Happy path: update description and color, returns updated label."""
    updated = ClassificationLabel(
        id=1,
        name="CONFLICT",
        description="Updated description",
        color="#ff0000",
        enabled=True,
        created_at="2026-03-21T10:00:00",
    )
    mock = MagicMock()
    mock.update_label.return_value = updated

    with _build_app(mock) as client:
        resp = client.patch(
            "/api/classification/labels/1",
            json={"description": "Updated description", "color": "#ff0000"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["description"] == "Updated description"
    assert body["color"] == "#ff0000"
    mock.update_label.assert_called_once_with(
        1, description="Updated description", color="#ff0000", enabled=None
    )


def test_update_label_toggle_enabled():
    """Updating only the enabled flag works."""
    mock = MagicMock()
    mock.update_label.return_value = ClassificationLabel(
        id=2,
        name="POLITICS",
        description="Politics",
        color="#a9c7ff",
        enabled=False,
        created_at="2026-03-21T10:00:00",
    )

    with _build_app(mock) as client:
        resp = client.patch("/api/classification/labels/2", json={"enabled": False})

    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
    mock.update_label.assert_called_once_with(2, description=None, color=None, enabled=False)


def test_update_label_not_found_returns_404():
    """When update_label returns None (no matching row), endpoint returns 404."""
    mock = MagicMock()
    mock.update_label.return_value = None

    with _build_app(mock) as client:
        resp = client.patch("/api/classification/labels/999", json={"color": "#fff"})

    assert resp.status_code == 404
    assert "999" in resp.json()["error"]


# ---------------------------------------------------------------------------
# DELETE /api/classification/labels/{id}
# ---------------------------------------------------------------------------


def test_delete_label_success():
    """Happy path: label is deleted and response contains ok and label_id."""
    mock = MagicMock()
    mock.delete_label.return_value = True

    with _build_app(mock) as client:
        resp = client.delete("/api/classification/labels/3")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["label_id"] == 3
    mock.delete_label.assert_called_once_with(3)


def test_delete_label_not_found_returns_404():
    """When delete_label returns False (no matching row), endpoint returns 404."""
    mock = MagicMock()
    mock.delete_label.return_value = False

    with _build_app(mock) as client:
        resp = client.delete("/api/classification/labels/999")

    assert resp.status_code == 404
    assert "999" in resp.json()["error"]
