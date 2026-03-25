"""Tests for graph relation-type CRUD and graph query endpoints.

Follows the same patterns as test_attribution.py: inject mock clients via
create_app() keyword arguments and test with FastAPI's TestClient. All
synchronous client methods are MagicMocks — run_in_executor hands them off to
a thread, but TestClient drives the event loop synchronously so the mocks are
called exactly as if they were real blocking calls.
"""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from monitoring_api.relation_type_client import RelationType
from monitoring_api.server import create_app

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_mocks(
    relation_type_mock: MagicMock | None = None,
    graph_mock: MagicMock | None = None,
) -> dict:
    """Build a full set of mock clients for create_app.

    All infrastructure clients are stubbed out so startup doesn't attempt
    real connections. Only the graph-specific mocks are configurable because
    those are the only ones the new endpoints touch.
    """
    docker = MagicMock()
    docker.get_containers.return_value = []

    rabbitmq = AsyncMock()
    rabbitmq.get_queues.return_value = []
    rabbitmq.get_exchanges.return_value = []
    rabbitmq.aclose.return_value = None

    db = MagicMock()
    db.get_stats.return_value = None

    article = MagicMock()
    label = MagicMock()
    label.get_labels.return_value = []
    role_type = MagicMock()
    role_type.get_role_types.return_value = []

    return {
        "docker_client": docker,
        "rabbitmq_client": rabbitmq,
        "db_client": db,
        "article_client": article,
        "label_client": label,
        "role_type_client": role_type,
        "relation_type_client": relation_type_mock or MagicMock(),
        "graph_client": graph_mock or MagicMock(),
    }


def _build_app(
    relation_type_mock: MagicMock | None = None,
    graph_mock: MagicMock | None = None,
) -> TestClient:
    mocks = _make_mocks(relation_type_mock, graph_mock)
    app = create_app(**mocks)
    return TestClient(app)


def _sample_relation_type(
    rt_id: int = 1,
    name: str = "ALLY_OF",
    directed: bool = True,
) -> RelationType:
    return RelationType(
        id=rt_id,
        name=name,
        description="Two entities are allied",
        color="#76A9FA",
        directed=directed,
        enabled=True,
        created_at="2026-03-22T10:00:00",
    )


# ---------------------------------------------------------------------------
# GET /api/graph/relation-types
# ---------------------------------------------------------------------------


def test_list_relation_types_returns_all():
    """Happy path: returns all relation type dicts with the directed field."""
    rt_mock = MagicMock()
    rt_mock.get_relation_types.return_value = [
        _sample_relation_type(1, "ALLY_OF", directed=True),
        _sample_relation_type(2, "OPPOSES", directed=False),
    ]

    with _build_app(relation_type_mock=rt_mock) as client:
        resp = client.get("/api/graph/relation-types")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["name"] == "ALLY_OF"
    assert body[0]["directed"] is True
    assert body[1]["name"] == "OPPOSES"
    assert body[1]["directed"] is False
    assert body[0]["enabled"] is True
    assert body[0]["color"] == "#76A9FA"


def test_list_relation_types_db_unavailable_returns_503():
    """When get_relation_types returns None the endpoint returns 503."""
    rt_mock = MagicMock()
    rt_mock.get_relation_types.return_value = None

    with _build_app(relation_type_mock=rt_mock) as client:
        resp = client.get("/api/graph/relation-types")

    assert resp.status_code == 503
    assert resp.json()["error"] == "unavailable"


def test_list_relation_types_empty_returns_empty_list():
    """When the table is empty the endpoint returns an empty list."""
    rt_mock = MagicMock()
    rt_mock.get_relation_types.return_value = []

    with _build_app(relation_type_mock=rt_mock) as client:
        resp = client.get("/api/graph/relation-types")

    assert resp.status_code == 200
    assert resp.json() == []


def test_list_relation_types_client_none_returns_503():
    """When no relation_type_client is injected the endpoint returns 503."""
    mocks = _make_mocks()
    mocks["relation_type_client"] = None
    app = create_app(**mocks)

    with TestClient(app) as client:
        resp = client.get("/api/graph/relation-types")

    assert resp.status_code == 503
    assert resp.json()["error"] == "unavailable"


# ---------------------------------------------------------------------------
# POST /api/graph/relation-types
# ---------------------------------------------------------------------------


def test_create_relation_type_success():
    """Happy path: valid body creates a relation type and returns 201."""
    rt_mock = MagicMock()
    rt_mock.create_relation_type.return_value = _sample_relation_type(5, "CONTROLS")

    with _build_app(relation_type_mock=rt_mock) as client:
        resp = client.post(
            "/api/graph/relation-types",
            json={
                "name": "CONTROLS",
                "description": "Entity A controls entity B",
                "color": "#a3e635",
                "directed": True,
            },
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == 5
    assert body["name"] == "CONTROLS"
    rt_mock.create_relation_type.assert_called_once_with(
        "CONTROLS", "Entity A controls entity B", "#a3e635", True
    )


def test_create_relation_type_default_color_and_directed():
    """color defaults to '#76A9FA' and directed defaults to True when omitted."""
    rt_mock = MagicMock()
    rt_mock.create_relation_type.return_value = _sample_relation_type(6, "FUNDS")

    with _build_app(relation_type_mock=rt_mock) as client:
        resp = client.post(
            "/api/graph/relation-types",
            json={"name": "FUNDS", "description": "Entity A funds entity B"},
        )

    assert resp.status_code == 201
    rt_mock.create_relation_type.assert_called_once_with(
        "FUNDS", "Entity A funds entity B", "#76A9FA", True
    )


def test_create_relation_type_duplicate_returns_409():
    """When create_relation_type returns None the endpoint returns 409."""
    rt_mock = MagicMock()
    rt_mock.create_relation_type.return_value = None

    with _build_app(relation_type_mock=rt_mock) as client:
        resp = client.post(
            "/api/graph/relation-types",
            json={"name": "ALLY_OF", "description": "Duplicate", "color": "#000"},
        )

    assert resp.status_code == 409
    assert "ALLY_OF" in resp.json()["error"]


def test_create_relation_type_missing_required_fields_returns_422():
    """Missing name or description returns 422 from Pydantic validation."""
    rt_mock = MagicMock()

    with _build_app(relation_type_mock=rt_mock) as client:
        resp = client.post("/api/graph/relation-types", json={"name": "NO_DESC"})

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/graph/relation-types/{id}
# ---------------------------------------------------------------------------


def test_update_relation_type_success():
    """Happy path: update description and color, returns updated relation type."""
    updated = RelationType(
        id=1,
        name="ALLY_OF",
        description="Updated description",
        color="#ff0000",
        directed=True,
        enabled=True,
        created_at="2026-03-22T10:00:00",
    )
    rt_mock = MagicMock()
    rt_mock.update_relation_type.return_value = updated

    with _build_app(relation_type_mock=rt_mock) as client:
        resp = client.patch(
            "/api/graph/relation-types/1",
            json={"description": "Updated description", "color": "#ff0000"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["description"] == "Updated description"
    assert body["color"] == "#ff0000"
    rt_mock.update_relation_type.assert_called_once_with(
        1, description="Updated description", color="#ff0000", directed=None, enabled=None
    )


def test_update_relation_type_toggle_directed():
    """Updating only the directed flag is forwarded correctly."""
    rt_mock = MagicMock()
    rt_mock.update_relation_type.return_value = RelationType(
        id=2,
        name="ALLY_OF",
        description="x",
        color="#fff",
        directed=False,
        enabled=True,
        created_at="2026-03-22T10:00:00",
    )

    with _build_app(relation_type_mock=rt_mock) as client:
        resp = client.patch("/api/graph/relation-types/2", json={"directed": False})

    assert resp.status_code == 200
    assert resp.json()["directed"] is False
    rt_mock.update_relation_type.assert_called_once_with(
        2, description=None, color=None, directed=False, enabled=None
    )


def test_update_relation_type_toggle_enabled():
    """Updating only the enabled flag works."""
    rt_mock = MagicMock()
    rt_mock.update_relation_type.return_value = RelationType(
        id=3,
        name="CONTROLS",
        description="x",
        color="#fff",
        directed=True,
        enabled=False,
        created_at="2026-03-22T10:00:00",
    )

    with _build_app(relation_type_mock=rt_mock) as client:
        resp = client.patch("/api/graph/relation-types/3", json={"enabled": False})

    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
    rt_mock.update_relation_type.assert_called_once_with(
        3, description=None, color=None, directed=None, enabled=False
    )


def test_update_relation_type_not_found_returns_404():
    """When update_relation_type returns None the endpoint returns 404."""
    rt_mock = MagicMock()
    rt_mock.update_relation_type.return_value = None

    with _build_app(relation_type_mock=rt_mock) as client:
        resp = client.patch("/api/graph/relation-types/999", json={"color": "#fff"})

    assert resp.status_code == 404
    assert "999" in resp.json()["error"]


# ---------------------------------------------------------------------------
# DELETE /api/graph/relation-types/{id}
# ---------------------------------------------------------------------------


def test_delete_relation_type_success():
    """Happy path: relation type is deleted and response contains ok and relation_type_id."""
    rt_mock = MagicMock()
    rt_mock.delete_relation_type.return_value = True

    with _build_app(relation_type_mock=rt_mock) as client:
        resp = client.delete("/api/graph/relation-types/7")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["relation_type_id"] == 7
    rt_mock.delete_relation_type.assert_called_once_with(7)


def test_delete_relation_type_not_found_returns_404():
    """When delete_relation_type returns False the endpoint returns 404."""
    rt_mock = MagicMock()
    rt_mock.delete_relation_type.return_value = False

    with _build_app(relation_type_mock=rt_mock) as client:
        resp = client.delete("/api/graph/relation-types/999")

    assert resp.status_code == 404
    assert "999" in resp.json()["error"]


# ---------------------------------------------------------------------------
# GET /api/graph/relations
# ---------------------------------------------------------------------------


def _sample_graph_result() -> dict:
    return {
        "nodes": [
            {"qid": "Q794", "name": "Iran", "entity_type": "country"},
            {"qid": "Q30", "name": "United States", "entity_type": "country"},
        ],
        "edges": [
            {
                "source": "Q794",
                "target": "Q30",
                "relation_type": "OPPOSES",
                "display_strength": 0.72,
                "base_strength": 0.8,
                "last_seen": "2026-03-20T12:00:00+00:00",
                "first_seen": "2026-01-01T00:00:00+00:00",
                "article_count": 14,
            }
        ],
    }


def test_get_graph_relations_default_params():
    """Happy path: returns nodes and edges with default parameters."""
    g_mock = MagicMock()
    g_mock.get_graph.return_value = _sample_graph_result()

    with _build_app(graph_mock=g_mock) as client:
        resp = client.get("/api/graph/relations")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["nodes"]) == 2
    assert len(body["edges"]) == 1
    assert body["edges"][0]["relation_type"] == "OPPOSES"

    g_mock.get_graph.assert_called_once_with(
        lambda_decay=0.01,
        min_strength=0.1,
        corroboration=0.5,
        relation_types=None,
        limit=200,
    )


def test_get_graph_relations_custom_params():
    """Custom query params are forwarded to get_graph correctly."""
    g_mock = MagicMock()
    g_mock.get_graph.return_value = {"nodes": [], "edges": []}

    with _build_app(graph_mock=g_mock) as client:
        resp = client.get(
            "/api/graph/relations"
            "?lambda_decay=0.001&min_strength=0.05&relation_types=ALLY_OF,CONTROLS&limit=50"
        )

    assert resp.status_code == 200
    g_mock.get_graph.assert_called_once_with(
        lambda_decay=0.001,
        min_strength=0.05,
        corroboration=0.5,
        relation_types=["ALLY_OF", "CONTROLS"],
        limit=50,
    )


def test_get_graph_relations_limit_capped_at_500():
    """A limit above 500 is capped to 500 before being passed to the client."""
    g_mock = MagicMock()
    g_mock.get_graph.return_value = {"nodes": [], "edges": []}

    with _build_app(graph_mock=g_mock) as client:
        client.get("/api/graph/relations?limit=9999")

    _, kwargs = g_mock.get_graph.call_args
    assert kwargs["limit"] == 500


def test_get_graph_relations_empty_relation_types_means_no_filter():
    """An empty relation_types query param results in relation_types=None (no filter)."""
    g_mock = MagicMock()
    g_mock.get_graph.return_value = {"nodes": [], "edges": []}

    with _build_app(graph_mock=g_mock) as client:
        client.get("/api/graph/relations?relation_types=")

    _, kwargs = g_mock.get_graph.call_args
    assert kwargs["relation_types"] is None


def test_get_graph_relations_graph_client_none_returns_503():
    """When no graph_client is injected the endpoint returns 503."""
    mocks = _make_mocks()
    mocks["graph_client"] = None
    app = create_app(**mocks)

    with TestClient(app) as client:
        resp = client.get("/api/graph/relations")

    assert resp.status_code == 503
    assert resp.json()["error"] == "unavailable"


def test_get_graph_relations_returns_empty_graph_on_no_results():
    """When the graph has no surviving edges after filtering, returns empty nodes/edges."""
    g_mock = MagicMock()
    g_mock.get_graph.return_value = {"nodes": [], "edges": []}

    with _build_app(graph_mock=g_mock) as client:
        resp = client.get("/api/graph/relations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["nodes"] == []
    assert body["edges"] == []
