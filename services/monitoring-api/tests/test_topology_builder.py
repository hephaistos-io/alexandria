"""Tests for topology_builder.build_topology().

The topology builder is a pure function — it takes pipeline labels and RabbitMQ
bindings as plain data and returns a PipelineTopology. No mocking is needed.

We test three levels:
  1. The builder in isolation with hand-crafted data (unit tests).
  2. The /api/topology endpoint via TestClient to verify HTTP integration.

Conventions from the existing test_server.py are followed:
  - Dependency injection via create_app() constructor args.
  - AsyncMock for async RabbitMQ methods, MagicMock for sync Docker methods.
"""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from monitoring_api.docker_client import PipelineLabels
from monitoring_api.rabbitmq_client import BindingInfo
from monitoring_api.server import create_app
from monitoring_api.topology_builder import (
    PipelineTopology,
    build_topology,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _labels(**kwargs) -> PipelineLabels:
    """Create a PipelineLabels with all fields defaulting to None."""
    defaults = dict(
        inputs=None,
        outputs=None,
        stores=None,
        reads=None,
        writes=None,
        role=None,
        icon=None,
        label=None,
        sublabel=None,
        accent=None,
    )
    defaults.update(kwargs)
    return PipelineLabels(**defaults)


def _stage_ids(topo: PipelineTopology) -> set[str]:
    return {s.id for s in topo.stages}


def _connections(topo: PipelineTopology) -> list[tuple[str, str, bool]]:
    """Return connections as (from_id, to_id, dashed) tuples for easy assertion."""
    return [(c.from_id, c.to_id, c.dashed) for c in topo.connections]


def _make_docker_client(labels: dict[str, PipelineLabels]) -> MagicMock:
    mock = MagicMock()
    mock.get_containers.return_value = []
    mock.get_pipeline_labels.return_value = labels
    return mock


def _make_rabbitmq_client(bindings: list[BindingInfo] | None = None) -> AsyncMock:
    mock = AsyncMock()
    mock.get_queues.return_value = []
    mock.get_exchanges.return_value = []
    mock.get_bindings.return_value = bindings or []
    mock.aclose.return_value = None
    return mock


# ---------------------------------------------------------------------------
# Unit tests: build_topology() as a pure function
# ---------------------------------------------------------------------------


class TestBuildTopologyStages:
    def test_empty_labels_returns_empty_topology(self):
        topo = build_topology({}, [])
        assert topo.stages == []
        assert topo.connections == []

    def test_single_fetcher_creates_service_and_queue(self):
        """A fetcher with only outputs creates one service stage and one queue stage."""
        labels = {
            "article-fetcher-bbc": _labels(
                outputs="queue:articles.rss",
                icon="rss_feed",
                label="BBC",
            )
        }
        topo = build_topology(labels, [])

        assert "article-fetcher-bbc" in _stage_ids(topo)
        assert "queue-articles.rss" in _stage_ids(topo)

    def test_service_stage_has_correct_match(self):
        labels = {"article-fetcher-bbc": _labels(outputs="queue:articles.rss")}
        topo = build_topology(labels, [])

        service = next(s for s in topo.stages if s.id == "article-fetcher-bbc")
        assert service.match.service == "article-fetcher-bbc"
        assert service.match.queue is None
        assert service.match.exchange is None

    def test_queue_stage_has_correct_match(self):
        labels = {"article-fetcher-bbc": _labels(outputs="queue:articles.rss")}
        topo = build_topology(labels, [])

        queue = next(s for s in topo.stages if s.id == "queue-articles.rss")
        assert queue.match.queue == "articles.rss"
        assert queue.match.service is None

    def test_queue_stage_visual(self):
        labels = {"article-fetcher-bbc": _labels(outputs="queue:articles.rss")}
        topo = build_topology(labels, [])

        queue = next(s for s in topo.stages if s.id == "queue-articles.rss")
        assert queue.visual.nodeType == "transport"
        assert queue.visual.icon == "inbox"
        assert queue.visual.variant == "primary"
        assert queue.scalable is False

    def test_exchange_stage_created_for_exchange_output(self):
        labels = {
            "article-scraper": _labels(
                inputs="queue:articles.rss",
                outputs="exchange:articles.scraped",
            )
        }
        topo = build_topology(labels, [])

        assert "exchange-articles.scraped" in _stage_ids(topo)
        exchange = next(s for s in topo.stages if s.id == "exchange-articles.scraped")
        assert exchange.visual.nodeType == "transport"
        assert exchange.visual.icon == "call_split"
        assert exchange.visual.variant == "tertiary"
        assert exchange.match.exchange == "articles.scraped"

    def test_service_with_icon_and_sublabel(self):
        labels = {
            "article-scraper": _labels(
                inputs="queue:articles.rss",
                outputs="exchange:articles.scraped",
                icon="language",
                sublabel="HTML → content",
            )
        }
        topo = build_topology(labels, [])

        service = next(s for s in topo.stages if s.id == "article-scraper")
        assert service.visual.icon == "language"
        assert service.visual.sublabel == "HTML → content"

    def test_store_service_created(self):
        """A service with role='store' becomes a service stage (not transport)."""
        labels = {"postgres": _labels(role="store", icon="database", sublabel="persistent store")}
        topo = build_topology(labels, [])

        assert "postgres" in _stage_ids(topo)
        pg = next(s for s in topo.stages if s.id == "postgres")
        assert pg.visual.nodeType == "service"
        assert pg.match.service == "postgres"

    def test_shared_queue_not_duplicated(self):
        """Multiple fetchers writing to the same queue produce only one queue stage."""
        labels = {
            "article-fetcher-bbc": _labels(outputs="queue:articles.rss"),
            "article-fetcher-swissinfo": _labels(outputs="queue:articles.rss"),
            "article-fetcher-aljazeera": _labels(outputs="queue:articles.rss"),
        }
        topo = build_topology(labels, [])

        queue_stages = [s for s in topo.stages if s.id == "queue-articles.rss"]
        assert len(queue_stages) == 1

    def test_service_scalable_flag(self):
        labels = {"article-fetcher-bbc": _labels(outputs="queue:articles.rss")}
        topo = build_topology(labels, [])

        service = next(s for s in topo.stages if s.id == "article-fetcher-bbc")
        assert service.scalable is True

    def test_store_service_not_scalable(self):
        """Store-role services (postgres, redis) should not be marked scalable."""
        labels = {"postgres": _labels(role="store", icon="database")}
        topo = build_topology(labels, [])

        pg = next(s for s in topo.stages if s.id == "postgres")
        assert pg.scalable is False


class TestMalformedSpecs:
    """Malformed transport specs should be skipped with a warning, not crash."""

    def test_missing_colon_in_outputs_skipped(self):
        """A spec like 'articles.rss' (no 'queue:' prefix) is skipped."""
        labels = {"article-fetcher-bbc": _labels(outputs="articles.rss")}
        topo = build_topology(labels, [])

        # Service stage exists, but no transport stage was created.
        assert _stage_ids(topo) == {"article-fetcher-bbc"}
        assert topo.connections == []

    def test_missing_colon_in_inputs_skipped(self):
        labels = {"scraper": _labels(inputs="articles.rss")}
        topo = build_topology(labels, [])

        assert _stage_ids(topo) == {"scraper"}
        assert topo.connections == []

    def test_empty_name_after_colon_skipped(self):
        """'queue:' (empty name) is invalid and should be skipped."""
        labels = {"fetcher": _labels(outputs="queue:")}
        topo = build_topology(labels, [])

        assert _stage_ids(topo) == {"fetcher"}
        assert topo.connections == []

    def test_unknown_kind_skipped(self):
        """'topic:foo' is not a valid kind and should be skipped."""
        labels = {"fetcher": _labels(outputs="topic:foo")}
        topo = build_topology(labels, [])

        assert _stage_ids(topo) == {"fetcher"}
        assert topo.connections == []

    def test_valid_specs_still_work(self):
        """Sanity check: valid specs still create transport stages."""
        labels = {"fetcher": _labels(outputs="queue:articles.rss")}
        topo = build_topology(labels, [])

        assert "queue-articles.rss" in _stage_ids(topo)


class TestBuildTopologyConnections:
    def test_service_to_queue_connection(self):
        """A service with outputs=queue:X creates service → queue-X connection."""
        labels = {"article-fetcher-bbc": _labels(outputs="queue:articles.rss")}
        topo = build_topology(labels, [])

        conns = _connections(topo)
        assert ("article-fetcher-bbc", "queue-articles.rss", False) in conns

    def test_queue_to_service_connection(self):
        """A service with inputs=queue:X creates queue-X → service connection."""
        labels = {
            "article-fetcher-bbc": _labels(outputs="queue:articles.rss"),
            "article-scraper": _labels(
                inputs="queue:articles.rss",
                outputs="exchange:articles.scraped",
            ),
        }
        topo = build_topology(labels, [])

        conns = _connections(topo)
        assert ("queue-articles.rss", "article-scraper", False) in conns

    def test_service_to_exchange_connection(self):
        labels = {
            "article-scraper": _labels(
                inputs="queue:articles.rss",
                outputs="exchange:articles.scraped",
            )
        }
        topo = build_topology(labels, [])

        conns = _connections(topo)
        assert ("article-scraper", "exchange-articles.scraped", False) in conns

    def test_store_connection_is_dashed(self):
        """Connections from services to their stores are dashed (side-channel)."""
        labels = {
            "article-store": _labels(
                inputs="queue:articles.training",
                stores="postgres",
                icon="storage",
            ),
            "postgres": _labels(role="store", icon="database"),
        }
        topo = build_topology(labels, [])

        conns = _connections(topo)
        assert ("article-store", "postgres", True) in conns

    def test_store_connection_missing_store_service_skipped(self):
        """If a 'stores' reference points to a service not in labels, no crash."""
        labels = {
            "article-store": _labels(inputs="queue:articles.training", stores="postgres"),
            # postgres is NOT in labels here
        }
        topo = build_topology(labels, [])
        # Should not raise and should produce no store connection.
        conns = _connections(topo)
        assert not any(c[1] == "postgres" for c in conns)

    def test_exchange_to_queue_binding_connection(self):
        """RabbitMQ bindings produce dashed exchange→queue connections."""
        labels = {
            "article-scraper": _labels(
                inputs="queue:articles.rss",
                outputs="exchange:articles.scraped",
            ),
            "ner-tagger": _labels(
                inputs="queue:articles.raw",
                outputs="queue:articles.tagged",
            ),
        }
        bindings = [
            BindingInfo(
                source="articles.scraped",
                destination="articles.raw",
                routing_key="",
            )
        ]
        topo = build_topology(labels, bindings)

        conns = _connections(topo)
        assert ("exchange-articles.scraped", "queue-articles.raw", True) in conns

    def test_binding_ignored_if_exchange_not_in_stages(self):
        """Bindings referencing unknown exchanges are silently ignored."""
        labels = {"ner-tagger": _labels(inputs="queue:articles.raw")}
        bindings = [
            BindingInfo(
                source="unknown.exchange",
                destination="articles.raw",
                routing_key="",
            )
        ]
        topo = build_topology(labels, bindings)
        # Should not crash; the orphan binding is just dropped.
        conns = _connections(topo)
        assert not any(c[0] == "exchange-unknown.exchange" for c in conns)

    def test_duplicate_bindings_deduplicated(self):
        """Multiple bindings between the same exchange and queue produce one edge."""
        labels = {
            "scraper": _labels(inputs="queue:articles.rss", outputs="exchange:articles.scraped"),
            "tagger": _labels(inputs="queue:articles.raw"),
        }
        bindings = [
            BindingInfo(source="articles.scraped", destination="articles.raw", routing_key="key1"),
            BindingInfo(source="articles.scraped", destination="articles.raw", routing_key="key2"),
            BindingInfo(source="articles.scraped", destination="articles.raw", routing_key="key3"),
        ]
        topo = build_topology(labels, bindings)
        conns = _connections(topo)
        expected = ("exchange-articles.scraped", "queue-articles.raw", True)
        binding_edges = [c for c in conns if c == expected]
        assert len(binding_edges) == 1


class TestBuildTopologyColumns:
    def test_source_service_at_column_0(self):
        """A fetcher with no inputs starts at column 0."""
        labels = {"article-fetcher-bbc": _labels(outputs="queue:articles.rss")}
        topo = build_topology(labels, [])

        fetcher = next(s for s in topo.stages if s.id == "article-fetcher-bbc")
        assert fetcher.column == 0

    def test_queue_after_source_at_column_1(self):
        labels = {"article-fetcher-bbc": _labels(outputs="queue:articles.rss")}
        topo = build_topology(labels, [])

        queue = next(s for s in topo.stages if s.id == "queue-articles.rss")
        assert queue.column == 1

    def test_columns_increase_through_pipeline(self):
        """Columns increment through a linear chain: fetcher→queue→scraper→exchange."""
        labels = {
            "article-fetcher-bbc": _labels(outputs="queue:articles.rss"),
            "article-scraper": _labels(
                inputs="queue:articles.rss",
                outputs="exchange:articles.scraped",
            ),
        }
        topo = build_topology(labels, [])

        by_id = {s.id: s for s in topo.stages}
        assert by_id["article-fetcher-bbc"].column == 0
        assert by_id["queue-articles.rss"].column == 1
        assert by_id["article-scraper"].column == 2
        assert by_id["exchange-articles.scraped"].column == 3

    def test_multiple_sources_converge_to_queue(self):
        """Three fetchers at column 0 all feed one queue at column 1."""
        labels = {
            "article-fetcher-bbc": _labels(outputs="queue:articles.rss"),
            "article-fetcher-swissinfo": _labels(outputs="queue:articles.rss"),
            "article-fetcher-aljazeera": _labels(outputs="queue:articles.rss"),
        }
        topo = build_topology(labels, [])

        by_id = {s.id: s for s in topo.stages}
        assert by_id["article-fetcher-bbc"].column == 0
        assert by_id["article-fetcher-swissinfo"].column == 0
        assert by_id["article-fetcher-aljazeera"].column == 0
        assert by_id["queue-articles.rss"].column == 1

    def test_store_connections_do_not_push_stores_via_bfs(self):
        """Dashed store/writes connections (non-layout) don't push stores rightward via BFS."""
        labels = {
            "article-store": _labels(inputs="queue:articles.training", stores="postgres"),
            "event-detector": _labels(reads="postgres"),
            "postgres": _labels(role="store", icon="database"),
        }
        topo = build_topology(labels, [])

        by_id = {s.id: s for s in topo.stages}
        # Postgres has both incoming (stores from article-store) and outgoing
        # (reads to event-detector) so the sink rule doesn't apply. Its BFS
        # column stays at 0 because 'stores' edges are non-layout.
        assert by_id["postgres"].column == 0

    def test_input_only_store_placed_at_last_column(self):
        """A store with only incoming connections is pushed to the last column."""
        labels = {
            "fetcher": _labels(outputs="queue:articles.rss", stores="redis"),
            "redis": _labels(role="store", icon="cached"),
        }
        topo = build_topology(labels, [])

        by_id = {s.id: s for s in topo.stages}
        max_col = max(s.column for s in topo.stages)
        # Redis only has incoming store connections → sink → last column.
        assert by_id["redis"].column == max_col
        assert by_id["redis"].column > 0

    def test_full_pipeline_columns(self):
        """End-to-end column assignment for the full Alexandria pipeline."""
        labels = {
            "article-fetcher-bbc": _labels(outputs="queue:articles.rss"),
            "article-fetcher-swissinfo": _labels(outputs="queue:articles.rss"),
            "article-fetcher-aljazeera": _labels(outputs="queue:articles.rss"),
            "article-scraper": _labels(
                inputs="queue:articles.rss",
                outputs="exchange:articles.scraped",
            ),
            "ner-tagger": _labels(
                inputs="queue:articles.raw",
                outputs="queue:articles.tagged",
            ),
            "entity-resolver": _labels(
                inputs="queue:articles.tagged",
                outputs="queue:articles.resolved",
                stores="redis",
            ),
            "article-store": _labels(
                inputs="queue:articles.training",
                stores="postgres",
            ),
            "postgres": _labels(role="store"),
            "redis": _labels(role="store"),
        }
        bindings = [
            BindingInfo(source="articles.scraped", destination="articles.raw", routing_key=""),
        ]
        topo = build_topology(labels, bindings)

        by_id = {s.id: s for s in topo.stages}

        # Sources (no predecessors) must be at column 0.
        assert by_id["article-fetcher-bbc"].column == 0
        assert by_id["article-fetcher-swissinfo"].column == 0
        assert by_id["article-fetcher-aljazeera"].column == 0

        # Downstream services must be strictly to the right of their inputs.
        assert by_id["article-scraper"].column > by_id["queue-articles.rss"].column
        assert by_id["exchange-articles.scraped"].column > by_id["article-scraper"].column
        assert by_id["queue-articles.raw"].column > by_id["exchange-articles.scraped"].column
        assert by_id["ner-tagger"].column > by_id["queue-articles.raw"].column


# ---------------------------------------------------------------------------
# Integration tests: /api/topology endpoint
# ---------------------------------------------------------------------------


class TestTopologyEndpoint:
    def test_topology_returns_200(self):
        docker = _make_docker_client({})
        rabbitmq = _make_rabbitmq_client()
        app = create_app(docker_client=docker, rabbitmq_client=rabbitmq)

        with TestClient(app) as client:
            resp = client.get("/api/topology")

        assert resp.status_code == 200

    def test_topology_empty_when_no_labels(self):
        docker = _make_docker_client({})
        rabbitmq = _make_rabbitmq_client()
        app = create_app(docker_client=docker, rabbitmq_client=rabbitmq)

        with TestClient(app) as client:
            resp = client.get("/api/topology")

        body = resp.json()
        assert body["stages"] == []
        assert body["connections"] == []

    def test_topology_returns_correct_shape(self):
        labels = {
            "article-fetcher-bbc": _labels(
                outputs="queue:articles.rss",
                icon="rss_feed",
                label="BBC",
            ),
            "article-scraper": _labels(
                inputs="queue:articles.rss",
                outputs="exchange:articles.scraped",
                icon="language",
                sublabel="HTML → content",
            ),
        }
        docker = _make_docker_client(labels)
        rabbitmq = _make_rabbitmq_client()
        app = create_app(docker_client=docker, rabbitmq_client=rabbitmq)

        with TestClient(app) as client:
            resp = client.get("/api/topology")

        body = resp.json()
        stage_ids = {s["id"] for s in body["stages"]}
        assert "article-fetcher-bbc" in stage_ids
        assert "queue-articles.rss" in stage_ids
        assert "article-scraper" in stage_ids
        assert "exchange-articles.scraped" in stage_ids

    def test_topology_connection_uses_from_key(self):
        """The frontend expects 'from', not 'from_id', in the JSON output."""
        labels = {"article-fetcher-bbc": _labels(outputs="queue:articles.rss")}
        docker = _make_docker_client(labels)
        rabbitmq = _make_rabbitmq_client()
        app = create_app(docker_client=docker, rabbitmq_client=rabbitmq)

        with TestClient(app) as client:
            resp = client.get("/api/topology")

        conns = resp.json()["connections"]
        assert len(conns) > 0
        # Each connection must have 'from', 'to', and 'dashed' keys.
        for conn in conns:
            assert "from" in conn
            assert "to" in conn
            assert "dashed" in conn
            assert "from_id" not in conn  # must NOT use the Python field name

    def test_topology_stage_visual_excludes_none_fields(self):
        """None visual fields should be omitted from JSON, not serialised as null."""
        labels = {"article-fetcher-bbc": _labels(outputs="queue:articles.rss", icon="rss_feed")}
        docker = _make_docker_client(labels)
        rabbitmq = _make_rabbitmq_client()
        app = create_app(docker_client=docker, rabbitmq_client=rabbitmq)

        with TestClient(app) as client:
            resp = client.get("/api/topology")

        stages = resp.json()["stages"]
        fetcher = next(s for s in stages if s["id"] == "article-fetcher-bbc")
        # sublabel was not set — should not appear in visual dict.
        assert "sublabel" not in fetcher["visual"]
        assert fetcher["visual"]["icon"] == "rss_feed"

    def test_topology_dashed_store_connection(self):
        """Store connections appear as dashed in the HTTP response."""
        labels = {
            "article-store": _labels(inputs="queue:articles.training", stores="postgres"),
            "postgres": _labels(role="store"),
        }
        docker = _make_docker_client(labels)
        rabbitmq = _make_rabbitmq_client()
        app = create_app(docker_client=docker, rabbitmq_client=rabbitmq)

        with TestClient(app) as client:
            resp = client.get("/api/topology")

        conns = resp.json()["connections"]
        store_conn = next(
            (c for c in conns if c["from"] == "article-store" and c["to"] == "postgres"),
            None,
        )
        assert store_conn is not None
        assert store_conn["dashed"] is True

    def test_topology_no_docker_client(self):
        """When docker_client is None in state, topology returns empty but 200."""
        # We can't easily inject None after lifespan, but we can pass an empty mock.
        docker = _make_docker_client({})
        rabbitmq = _make_rabbitmq_client()
        app = create_app(docker_client=docker, rabbitmq_client=rabbitmq)

        with TestClient(app) as client:
            resp = client.get("/api/topology")

        assert resp.status_code == 200
        assert resp.json()["stages"] == []


# ---------------------------------------------------------------------------
# Unit tests: db: transport specs
# ---------------------------------------------------------------------------


class TestCommaSeparatedSpecs:
    """Comma-separated inputs/outputs specs are split and processed individually."""

    def test_comma_separated_outputs_parsed(self):
        """Multiple comma-separated outputs each become their own stage."""
        labels = {
            "splitter": _labels(outputs="queue:articles.a,queue:articles.b")
        }
        topo = build_topology(labels, [])

        ids = _stage_ids(topo)
        assert "queue-articles.a" in ids
        assert "queue-articles.b" in ids

    def test_comma_separated_outputs_create_two_connections(self):
        labels = {"splitter": _labels(outputs="queue:articles.a,queue:articles.b")}
        topo = build_topology(labels, [])

        conns = _connections(topo)
        assert ("splitter", "queue-articles.a", False) in conns
        assert ("splitter", "queue-articles.b", False) in conns

    def test_malformed_spec_in_comma_list_skipped(self):
        """A bad spec in a comma list is skipped; valid siblings still work."""
        labels = {
            "svc": _labels(inputs="queue:articles.rss,BADSPEC,queue:articles.tagged")
        }
        topo = build_topology(labels, [])

        ids = _stage_ids(topo)
        assert "queue-articles.rss" in ids
        assert "queue-articles.tagged" in ids
        assert not any("BADSPEC" in sid for sid in ids)

    def test_whitespace_around_comma_is_stripped(self):
        """Spaces around the comma separator are tolerated."""
        labels = {
            "svc": _labels(inputs="queue:articles.rss , queue:articles.tagged")
        }
        topo = build_topology(labels, [])

        ids = _stage_ids(topo)
        assert "queue-articles.rss" in ids
        assert "queue-articles.tagged" in ids


# ---------------------------------------------------------------------------
# Unit tests: reads/writes directional store connections
# ---------------------------------------------------------------------------


class TestReadsWritesLabels:
    """The reads and writes labels create directional dashed store connections."""

    def test_reads_creates_store_to_service_connection(self):
        labels = {
            "postgres": _labels(role="store", icon="database"),
            "event-detector": _labels(reads="postgres"),
        }
        topo = build_topology(labels, [])

        conns = _connections(topo)
        assert ("postgres", "event-detector", True) in conns

    def test_writes_creates_service_to_store_connection(self):
        labels = {
            "postgres": _labels(role="store", icon="database"),
            "event-detector": _labels(writes="postgres"),
        }
        topo = build_topology(labels, [])

        conns = _connections(topo)
        assert ("event-detector", "postgres", True) in conns

    def test_reads_and_writes_same_store(self):
        """A service that both reads and writes postgres gets two connections."""
        labels = {
            "postgres": _labels(role="store", icon="database"),
            "event-detector": _labels(reads="postgres", writes="postgres"),
        }
        topo = build_topology(labels, [])

        conns = _connections(topo)
        assert ("postgres", "event-detector", True) in conns
        assert ("event-detector", "postgres", True) in conns

    def test_reads_skips_unknown_store(self):
        """reads referencing a non-existent store creates no connection."""
        labels = {"event-detector": _labels(reads="postgres")}
        topo = build_topology(labels, [])

        conns = _connections(topo)
        assert len(conns) == 0

    def test_reads_is_layout_affecting_writes_is_not(self):
        """reads connections affect layout (service comes after store);
        writes connections do not (avoids cycles)."""
        labels = {
            "postgres": _labels(role="store", icon="database"),
            "event-detector": _labels(reads="postgres", writes="postgres"),
        }
        topo = build_topology(labels, [])

        reads_conn = next(c for c in topo.connections if c.from_id == "postgres")
        writes_conn = next(c for c in topo.connections if c.from_id == "event-detector")
        assert reads_conn.affects_layout is True
        assert writes_conn.affects_layout is False
