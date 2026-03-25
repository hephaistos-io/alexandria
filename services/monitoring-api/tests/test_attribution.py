"""Tests for attribution role-type CRUD and labelling endpoints.

Follows the same patterns as test_label_endpoints.py and test_labelling.py:
inject mock clients via create_app() keyword arguments and test with FastAPI's
TestClient. All client methods are synchronous MagicMocks — run_in_executor is
handled transparently by TestClient.
"""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from monitoring_api.article_client import (
    AttributionArticlePage,
    AttributionArticleSummary,
    AttributionStats,
)
from monitoring_api.role_type_client import EntityRoleType
from monitoring_api.server import create_app

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_mocks(
    article_mock: MagicMock | None = None,
    role_type_mock: MagicMock | None = None,
) -> dict:
    """Build a minimal set of mocks for create_app.

    Provides all required clients so create_app doesn't try to connect to
    real infrastructure. Only article_mock and role_type_mock are configurable
    because that's all the attribution endpoints touch.
    """
    docker = MagicMock()
    docker.get_containers.return_value = []

    rabbitmq = AsyncMock()
    rabbitmq.get_queues.return_value = []
    rabbitmq.get_exchanges.return_value = []
    rabbitmq.aclose.return_value = None

    db = MagicMock()
    db.get_stats.return_value = None

    label = MagicMock()
    label.get_labels.return_value = []

    return {
        "docker_client": docker,
        "rabbitmq_client": rabbitmq,
        "db_client": db,
        "article_client": article_mock or MagicMock(),
        "label_client": label,
        "role_type_client": role_type_mock or MagicMock(),
    }


def _build_app(
    article_mock: MagicMock | None = None,
    role_type_mock: MagicMock | None = None,
) -> TestClient:
    mocks = _make_mocks(article_mock, role_type_mock)
    app = create_app(**mocks)
    return TestClient(app)


def _sample_role_type(role_type_id: int = 1, name: str = "AFFECTED") -> EntityRoleType:
    return EntityRoleType(
        id=role_type_id,
        name=name,
        description="Entities affected by the event",
        color="#76A9FA",
        enabled=True,
        created_at="2026-03-22T10:00:00",
    )


def _sample_attribution_page() -> AttributionArticlePage:
    return AttributionArticlePage(
        articles=[
            AttributionArticleSummary(
                id=10,
                origin="bbc",
                title="Iran floods kill dozens",
                summary="Floods in southern Iran kill dozens.",
                content="Full article content about Iran floods.",
                created_at="2026-03-22T08:00:00",
                entities=[{"id": "Q794", "label": "Iran"}],
                manual_entity_roles=None,
                entity_roles_labelled_at=None,
            ),
            AttributionArticleSummary(
                id=11,
                origin="reuters",
                title="US policy shift on aid",
                summary="Washington shifts foreign aid policy.",
                content="Full article content about US policy shift.",
                created_at="2026-03-22T09:00:00",
                entities=[{"id": "Q30", "label": "United States"}],
                manual_entity_roles={"Q30": "SOURCE"},
                entity_roles_labelled_at="2026-03-22T10:00:00",
            ),
        ],
        total=2,
        page=1,
        page_size=10,
    )


# ---------------------------------------------------------------------------
# GET /api/attribution/role-types
# ---------------------------------------------------------------------------


def test_list_role_types_returns_all():
    """Happy path: GET returns a list of role type dicts."""
    rt_mock = MagicMock()
    rt_mock.get_role_types.return_value = [
        _sample_role_type(1, "AFFECTED"),
        _sample_role_type(2, "SOURCE"),
    ]

    with _build_app(role_type_mock=rt_mock) as client:
        resp = client.get("/api/attribution/role-types")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["name"] == "AFFECTED"
    assert body[1]["name"] == "SOURCE"
    assert body[0]["enabled"] is True
    assert body[0]["color"] == "#76A9FA"


def test_list_role_types_db_unavailable_returns_503():
    """When get_role_types returns None the endpoint returns 503."""
    rt_mock = MagicMock()
    rt_mock.get_role_types.return_value = None

    with _build_app(role_type_mock=rt_mock) as client:
        resp = client.get("/api/attribution/role-types")

    assert resp.status_code == 503
    assert resp.json()["error"] == "unavailable"


def test_list_role_types_empty_returns_empty_list():
    """When the table is empty the endpoint returns an empty list."""
    rt_mock = MagicMock()
    rt_mock.get_role_types.return_value = []

    with _build_app(role_type_mock=rt_mock) as client:
        resp = client.get("/api/attribution/role-types")

    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# POST /api/attribution/role-types
# ---------------------------------------------------------------------------


def test_create_role_type_success():
    """Happy path: valid body creates a role type and returns it."""
    rt_mock = MagicMock()
    rt_mock.create_role_type.return_value = _sample_role_type(5, "ACTOR")

    with _build_app(role_type_mock=rt_mock) as client:
        resp = client.post(
            "/api/attribution/role-types",
            json={
                "name": "ACTOR",
                "description": "Primary actor in the event",
                "color": "#a3e635",
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 5
    assert body["name"] == "ACTOR"
    rt_mock.create_role_type.assert_called_once_with(
        "ACTOR", "Primary actor in the event", "#a3e635"
    )


def test_create_role_type_default_color():
    """Color defaults to '#76A9FA' when not provided."""
    rt_mock = MagicMock()
    rt_mock.create_role_type.return_value = _sample_role_type(6, "WITNESS")

    with _build_app(role_type_mock=rt_mock) as client:
        resp = client.post(
            "/api/attribution/role-types",
            json={"name": "WITNESS", "description": "Witness to the event"},
        )

    assert resp.status_code == 200
    rt_mock.create_role_type.assert_called_once_with("WITNESS", "Witness to the event", "#76A9FA")


def test_create_role_type_duplicate_returns_409():
    """When create_role_type returns None (e.g. duplicate name), endpoint returns 409."""
    rt_mock = MagicMock()
    rt_mock.create_role_type.return_value = None

    with _build_app(role_type_mock=rt_mock) as client:
        resp = client.post(
            "/api/attribution/role-types",
            json={"name": "AFFECTED", "description": "Duplicate", "color": "#000"},
        )

    assert resp.status_code == 409
    assert "AFFECTED" in resp.json()["error"]


def test_create_role_type_missing_required_fields_returns_422():
    """Missing name or description returns 422 from Pydantic validation."""
    rt_mock = MagicMock()

    with _build_app(role_type_mock=rt_mock) as client:
        resp = client.post("/api/attribution/role-types", json={"name": "ONLY_NAME"})

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/attribution/role-types/{id}
# ---------------------------------------------------------------------------


def test_update_role_type_success():
    """Happy path: update description and color, returns updated role type."""
    updated = EntityRoleType(
        id=1,
        name="AFFECTED",
        description="Updated description",
        color="#ff0000",
        enabled=True,
        created_at="2026-03-22T10:00:00",
    )
    rt_mock = MagicMock()
    rt_mock.update_role_type.return_value = updated

    with _build_app(role_type_mock=rt_mock) as client:
        resp = client.patch(
            "/api/attribution/role-types/1",
            json={"description": "Updated description", "color": "#ff0000"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["description"] == "Updated description"
    assert body["color"] == "#ff0000"
    rt_mock.update_role_type.assert_called_once_with(
        1, description="Updated description", color="#ff0000", enabled=None
    )


def test_update_role_type_toggle_enabled():
    """Updating only the enabled flag works."""
    rt_mock = MagicMock()
    rt_mock.update_role_type.return_value = EntityRoleType(
        id=2,
        name="SOURCE",
        description="Info source",
        color="#a9c7ff",
        enabled=False,
        created_at="2026-03-22T10:00:00",
    )

    with _build_app(role_type_mock=rt_mock) as client:
        resp = client.patch("/api/attribution/role-types/2", json={"enabled": False})

    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
    rt_mock.update_role_type.assert_called_once_with(2, description=None, color=None, enabled=False)


def test_update_role_type_not_found_returns_404():
    """When update_role_type returns None the endpoint returns 404."""
    rt_mock = MagicMock()
    rt_mock.update_role_type.return_value = None

    with _build_app(role_type_mock=rt_mock) as client:
        resp = client.patch("/api/attribution/role-types/999", json={"color": "#fff"})

    assert resp.status_code == 404
    assert "999" in resp.json()["error"]


# ---------------------------------------------------------------------------
# DELETE /api/attribution/role-types/{id}
# ---------------------------------------------------------------------------


def test_delete_role_type_success():
    """Happy path: role type is deleted and response contains ok and role_type_id."""
    rt_mock = MagicMock()
    rt_mock.delete_role_type.return_value = True

    with _build_app(role_type_mock=rt_mock) as client:
        resp = client.delete("/api/attribution/role-types/3")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["role_type_id"] == 3
    rt_mock.delete_role_type.assert_called_once_with(3)


def test_delete_role_type_not_found_returns_404():
    """When delete_role_type returns False the endpoint returns 404."""
    rt_mock = MagicMock()
    rt_mock.delete_role_type.return_value = False

    with _build_app(role_type_mock=rt_mock) as client:
        resp = client.delete("/api/attribution/role-types/999")

    assert resp.status_code == 404
    assert "999" in resp.json()["error"]


# ---------------------------------------------------------------------------
# GET /api/attribution/stats
# ---------------------------------------------------------------------------


def test_attribution_stats_returns_correct_shape():
    """Happy path: stats endpoint returns all four fields."""
    art_mock = MagicMock()
    art_mock.get_attribution_stats.return_value = AttributionStats(
        total_with_entities=50,
        annotated_count=20,
        unannotated_count=30,
        progress_percent=40.0,
    )

    with _build_app(article_mock=art_mock) as client:
        resp = client.get("/api/attribution/stats")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_with_entities"] == 50
    assert body["annotated_count"] == 20
    assert body["unannotated_count"] == 30
    assert body["progress_percent"] == 40.0


def test_attribution_stats_unavailable_returns_503():
    """When get_attribution_stats returns None the endpoint returns 503."""
    art_mock = MagicMock()
    art_mock.get_attribution_stats.return_value = None

    with _build_app(article_mock=art_mock) as client:
        resp = client.get("/api/attribution/stats")

    assert resp.status_code == 503
    assert resp.json()["error"] == "unavailable"


# ---------------------------------------------------------------------------
# GET /api/attribution/articles
# ---------------------------------------------------------------------------


def test_attribution_articles_default_params():
    """Articles endpoint with defaults returns correct shape and calls client correctly."""
    art_mock = MagicMock()
    art_mock.get_attribution_articles.return_value = _sample_attribution_page()

    with _build_app(article_mock=art_mock) as client:
        resp = client.get("/api/attribution/articles")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert len(body["articles"]) == 2
    assert body["articles"][0]["title"] == "Iran floods kill dozens"
    assert body["articles"][0]["manual_entity_roles"] is None
    assert body["articles"][1]["manual_entity_roles"] == {"Q30": "SOURCE"}

    art_mock.get_attribution_articles.assert_called_once_with(
        1, 10, "all", "date_ingested", "desc"
    )


def test_attribution_articles_filter_annotated():
    """Filter=annotated is passed through to the client."""
    art_mock = MagicMock()
    art_mock.get_attribution_articles.return_value = AttributionArticlePage(
        articles=[], total=0, page=1, page_size=10
    )

    with _build_app(article_mock=art_mock) as client:
        resp = client.get("/api/attribution/articles?filter=annotated")

    assert resp.status_code == 200
    art_mock.get_attribution_articles.assert_called_once_with(
        1, 10, "annotated", "date_ingested", "desc"
    )


def test_attribution_articles_filter_unannotated():
    """Filter=unannotated is passed through to the client."""
    art_mock = MagicMock()
    art_mock.get_attribution_articles.return_value = AttributionArticlePage(
        articles=[], total=0, page=1, page_size=10
    )

    with _build_app(article_mock=art_mock) as client:
        resp = client.get("/api/attribution/articles?filter=unannotated")

    assert resp.status_code == 200
    art_mock.get_attribution_articles.assert_called_once_with(
        1, 10, "unannotated", "date_ingested", "desc"
    )


def test_attribution_articles_invalid_filter_returns_422():
    """An invalid filter value returns 422."""
    art_mock = MagicMock()

    with _build_app(article_mock=art_mock) as client:
        resp = client.get("/api/attribution/articles?filter=bogus")

    assert resp.status_code == 422
    assert "Invalid filter" in resp.json()["error"]


def test_attribution_articles_invalid_sort_by_returns_422():
    """An invalid sort_by value returns 422."""
    art_mock = MagicMock()

    with _build_app(article_mock=art_mock) as client:
        resp = client.get("/api/attribution/articles?sort_by=bogus")

    assert resp.status_code == 422
    assert "Invalid sort_by" in resp.json()["error"]


def test_attribution_articles_invalid_sort_dir_returns_422():
    """An invalid sort_dir value returns 422."""
    art_mock = MagicMock()

    with _build_app(article_mock=art_mock) as client:
        resp = client.get("/api/attribution/articles?sort_dir=upward")

    assert resp.status_code == 422
    assert "Invalid sort_dir" in resp.json()["error"]


def test_attribution_articles_db_unavailable_returns_503():
    """When the client returns None the endpoint returns 503."""
    art_mock = MagicMock()
    art_mock.get_attribution_articles.return_value = None

    with _build_app(article_mock=art_mock) as client:
        resp = client.get("/api/attribution/articles")

    assert resp.status_code == 503
    assert resp.json()["error"] == "unavailable"


# ---------------------------------------------------------------------------
# PATCH /api/attribution/articles/{article_id}/roles
# ---------------------------------------------------------------------------


def test_update_roles_success():
    """Happy path: valid roles are saved and the endpoint returns ok."""
    art_mock = MagicMock()
    art_mock.update_entity_roles.return_value = True

    rt_mock = MagicMock()
    rt_mock.get_role_types.return_value = [
        _sample_role_type(1, "AFFECTED"),
        _sample_role_type(2, "SOURCE"),
    ]

    with _build_app(article_mock=art_mock, role_type_mock=rt_mock) as client:
        resp = client.patch(
            "/api/attribution/articles/42/roles",
            json={"roles": {"Q794": "AFFECTED", "Q30": "SOURCE"}},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["article_id"] == 42
    assert body["roles"] == {"Q794": "AFFECTED", "Q30": "SOURCE"}
    art_mock.update_entity_roles.assert_called_once_with(
        42, {"Q794": "AFFECTED", "Q30": "SOURCE"}
    )


def test_update_roles_invalid_role_name_returns_422():
    """A role name not in entity_role_types returns 422 with a descriptive error."""
    art_mock = MagicMock()

    rt_mock = MagicMock()
    rt_mock.get_role_types.return_value = [
        _sample_role_type(1, "AFFECTED"),
        _sample_role_type(2, "SOURCE"),
    ]

    with _build_app(article_mock=art_mock, role_type_mock=rt_mock) as client:
        resp = client.patch(
            "/api/attribution/articles/1/roles",
            json={"roles": {"Q794": "AFFECTED", "Q30": "MADE_UP_ROLE"}},
        )

    assert resp.status_code == 422
    body = resp.json()
    assert "Invalid role" in body["error"]
    assert "MADE_UP_ROLE" in body["error"]


def test_update_roles_clears_when_empty_dict():
    """An empty roles dict clears the annotation (sets manual_entity_roles to NULL)."""
    art_mock = MagicMock()
    art_mock.update_entity_roles.return_value = True

    rt_mock = MagicMock()
    rt_mock.get_role_types.return_value = [_sample_role_type(1, "AFFECTED")]

    with _build_app(article_mock=art_mock, role_type_mock=rt_mock) as client:
        resp = client.patch(
            "/api/attribution/articles/42/roles",
            json={"roles": {}},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["roles"] == {}
    # Validation is skipped for empty dict — update_entity_roles is called directly.
    art_mock.update_entity_roles.assert_called_once_with(42, {})


def test_update_roles_not_found_returns_404():
    """When update_entity_roles returns False the endpoint returns 404."""
    art_mock = MagicMock()
    art_mock.update_entity_roles.return_value = False

    rt_mock = MagicMock()
    rt_mock.get_role_types.return_value = [_sample_role_type(1, "AFFECTED")]

    with _build_app(article_mock=art_mock, role_type_mock=rt_mock) as client:
        resp = client.patch(
            "/api/attribution/articles/999/roles",
            json={"roles": {"Q794": "AFFECTED"}},
        )

    assert resp.status_code == 404
    assert "not found" in resp.json()["error"].lower()
