"""topology_builder — builds a PipelineTopology from Docker labels and RabbitMQ bindings.

This module is a pure function: given a dict of pipeline labels (from Docker) and
a list of exchange-to-queue bindings (from RabbitMQ), it produces a topology graph
that the frontend can render without any hard-coded service knowledge.

The output shape matches the TypeScript PipelineTopology interface:
  - stages: nodes in the graph (services, queues, exchanges, stores)
  - connections: directed edges between stages

Column assignment
-----------------
Columns represent horizontal position in the visual pipeline. We compute them via
a BFS (Breadth-First Search) topological sort:
  1. Build an adjacency list of source → [targets].
  2. Find all nodes with no incoming edges (sources) — they go in column 0.
  3. For each node, column = max(column of all predecessors) + 1.

This is a standard "longest path" calculation for DAGs. It ensures that even if
a node has multiple predecessors at different depths, it's placed to the right of
all of them.
"""

import logging
from collections import defaultdict, deque
from dataclasses import dataclass

from monitoring_api.docker_client import PipelineLabels
from monitoring_api.rabbitmq_client import BindingInfo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output data structures (serialised to JSON for the API response)
# ---------------------------------------------------------------------------


@dataclass
class StageMatch:
    """Criteria the frontend uses to match a live container or queue to this stage.

    Exactly one of 'service' or 'queue' or 'exchange' will be set.
    """

    service: str | None = None
    queue: str | None = None
    exchange: str | None = None


@dataclass
class StageVisual:
    """Visual rendering hints for the frontend."""

    nodeType: str  # "service" | "transport"
    icon: str | None = None
    label: str | None = None
    sublabel: str | None = None
    variant: str | None = None  # "primary" | "tertiary" etc.
    accent: str | None = None


@dataclass
class PipelineStage:
    id: str
    column: int
    match: StageMatch
    visual: StageVisual
    scalable: bool
    role: str | None = None


@dataclass
class StageConnection:
    from_id: str  # source stage id  (named 'from' in TS, but that's a Python keyword)
    to_id: str  # target stage id
    dashed: bool = False
    # False for side-channel edges (stores) excluded from column assignment.
    affects_layout: bool = True


@dataclass
class PipelineTopology:
    stages: list[PipelineStage]
    connections: list[StageConnection]


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_topology(
    pipeline_labels: dict[str, PipelineLabels],
    bindings: list[BindingInfo],
) -> PipelineTopology:
    """Build a PipelineTopology from Docker pipeline labels and RabbitMQ bindings.

    Args:
        pipeline_labels: Mapping of service_name -> PipelineLabels, as returned
                         by DockerClient.get_pipeline_labels().
        bindings:        List of exchange→queue bindings from RabbitMQClient.get_bindings().

    Returns:
        A PipelineTopology with all stages and connections, columns assigned via BFS.
    """
    stages: dict[str, PipelineStage] = {}
    connections: list[StageConnection] = []

    # --- Step 1: Build service stages ---
    # Each service with pipeline labels becomes a node.
    # Services with role="store" are infrastructure nodes (postgres, redis).
    for service_name, labels in pipeline_labels.items():
        stage_id = service_name

        stages[stage_id] = PipelineStage(
            id=stage_id,
            column=0,  # will be set by BFS later
            match=StageMatch(service=service_name),
            visual=StageVisual(
                nodeType="service",
                icon=labels.icon,
                # Always provide a label — the frontend's StageVisual.label is
                # required (non-optional). Fall back to the service name so
                # nodes always have visible text.
                label=labels.label or service_name,
                sublabel=labels.sublabel,
                accent=labels.accent,
            ),
            scalable=labels.role != "store",
            role=labels.role,
        )

        # --- Step 2: Build transport stages and connections for this service ---

        # Parse comma-separated transport specs from inputs/outputs labels.
        # Each spec has the form "kind:name" (e.g. "queue:articles.rss",
        # "exchange:articles.scraped", "db:events"). A single label value may
        # contain multiple specs: "db:articles,db:conflict_events".
        if labels.inputs is not None:
            for spec in labels.inputs.split(","):
                spec = spec.strip()
                if _is_valid_transport_spec(spec):
                    _ensure_transport_stage(spec, stages)
                    transport_id = _transport_id(spec)
                    connections.append(StageConnection(from_id=transport_id, to_id=stage_id))
                else:
                    logger.warning(
                        "Skipping malformed inputs spec %r on service %s",
                        spec,
                        service_name,
                    )

        if labels.outputs is not None:
            for spec in labels.outputs.split(","):
                spec = spec.strip()
                if _is_valid_transport_spec(spec):
                    _ensure_transport_stage(spec, stages)
                    transport_id = _transport_id(spec)
                    connections.append(StageConnection(from_id=stage_id, to_id=transport_id))
                else:
                    logger.warning(
                        "Skipping malformed outputs spec %r on service %s",
                        spec,
                        service_name,
                    )

        # Store connections are dashed (side-channel, not in the main flow).
        # Supports comma-separated values so a service can connect to multiple
        # stores (e.g. "postgres,neo4j" for monitoring-api).
        #
        # Three labels control direction:
        #   stores: service → store  (legacy, same direction as writes)
        #   reads:  store → service  (input from a store)
        #   writes: service → store  (output to a store)
        if labels.stores is not None:
            for store_name in labels.stores.split(","):
                store_name = store_name.strip()
                if store_name in pipeline_labels:
                    connections.append(
                        StageConnection(
                            from_id=stage_id,
                            to_id=store_name,
                            dashed=True,
                            affects_layout=False,
                        )
                    )

        if labels.reads is not None:
            for store_name in labels.reads.split(","):
                store_name = store_name.strip()
                if store_name in pipeline_labels:
                    # reads edges ARE layout-affecting: the service logically
                    # comes after the store it reads from. writes/stores stay
                    # non-layout to avoid cycles (A reads postgres, B writes
                    # postgres → no cycle in the layout graph).
                    connections.append(
                        StageConnection(
                            from_id=store_name,
                            to_id=stage_id,
                            dashed=True,
                            affects_layout=True,
                        )
                    )

        if labels.writes is not None:
            for store_name in labels.writes.split(","):
                store_name = store_name.strip()
                if store_name in pipeline_labels:
                    connections.append(
                        StageConnection(
                            from_id=stage_id,
                            to_id=store_name,
                            dashed=True,
                            affects_layout=False,
                        )
                    )

    # --- Step 3: Add exchange→queue connections from RabbitMQ bindings ---
    # These are dashed because they're infrastructure-level routing, not
    # direct service-to-service connections.
    # Deduplicate: RabbitMQ can have multiple bindings between the same
    # exchange and queue (different routing keys) — we only need one edge.
    seen_edges: set[tuple[str, str]] = set()
    for binding in bindings:
        exchange_id = f"exchange-{binding.source}"
        queue_id = f"queue-{binding.destination}"
        edge_key = (exchange_id, queue_id)
        # Only add the connection if both ends are in the graph and not already added.
        if exchange_id in stages and queue_id in stages and edge_key not in seen_edges:
            seen_edges.add(edge_key)
            connections.append(StageConnection(from_id=exchange_id, to_id=queue_id, dashed=True))

    # --- Step 4: Assign columns via BFS topological sort ---
    _assign_columns(stages, connections)

    return PipelineTopology(
        stages=list(stages.values()),
        connections=connections,
    )


_VALID_TRANSPORT_KINDS = {"queue", "exchange"}


def _is_valid_transport_spec(spec: str) -> bool:
    """Return True if the spec has the form 'queue:<name>' or 'exchange:<name>'."""
    kind, sep, name = spec.partition(":")
    return bool(sep) and kind in _VALID_TRANSPORT_KINDS and bool(name)


def _transport_id(spec: str) -> str:
    """Convert a label spec like 'queue:articles.rss' to a stage id like 'queue-articles.rss'.

    Caller must validate with _is_valid_transport_spec() first.
    """
    kind, _, name = spec.partition(":")
    return f"{kind}-{name}"


def _ensure_transport_stage(
    spec: str,
    stages: dict[str, PipelineStage],
) -> None:
    """Create a queue or exchange stage if it doesn't already exist.

    Transport nodes (queues, exchanges) don't come from Docker labels — they're
    implied by the inputs/outputs of services. We create them on-demand the first
    time a service references them.

    Caller must validate with _is_valid_transport_spec() first.
    """
    kind, _, name = spec.partition(":")
    stage_id = f"{kind}-{name}"

    if stage_id in stages:
        return  # Already created by a previous service.

    if kind == "queue":
        stages[stage_id] = PipelineStage(
            id=stage_id,
            column=0,
            match=StageMatch(queue=name),
            visual=StageVisual(
                nodeType="transport",
                label=name,
                icon="inbox",
                variant="primary",
            ),
            scalable=False,
        )
    elif kind == "exchange":
        # Exchange type (fanout/topic/direct) is on ExchangeInfo, not BindingInfo.
        # TODO: Thread ExchangeInfo into build_topology to enrich sublabel here.
        stages[stage_id] = PipelineStage(
            id=stage_id,
            column=0,
            match=StageMatch(exchange=name),
            visual=StageVisual(
                nodeType="transport",
                label=name,
                icon="call_split",
                variant="tertiary",
            ),
            scalable=False,
        )


def _assign_columns(
    stages: dict[str, PipelineStage],
    connections: list[StageConnection],
) -> None:
    """Assign column numbers via longest-path BFS (modified Kahn's algorithm).

    Each node's column = max(column of predecessors) + 1.
    Nodes with no predecessors start at column 0.

    Only edges with affects_layout=True are used for column calculation.
    Store connections (affects_layout=False) are excluded because they're
    side-channel relationships that should not affect horizontal positioning
    — and could introduce cycles (e.g. service → store → service).

    Runs in O(V + E) time: we build an adjacency list up front so the BFS
    inner loop only visits each edge once.
    """
    # Build in-degree count and adjacency list (source → list of targets).
    # Only consider layout-affecting edges to avoid cycles from store
    # connections and to keep stores from pushing services rightward.
    in_degree: dict[str, int] = {sid: 0 for sid in stages}
    successors: dict[str, list[str]] = defaultdict(list)

    for conn in connections:
        if not conn.affects_layout:
            continue
        if conn.from_id in stages and conn.to_id in stages:
            in_degree[conn.to_id] = in_degree.get(conn.to_id, 0) + 1
            successors[conn.from_id].append(conn.to_id)

    # Column of each stage (starts at 0).
    column: dict[str, int] = {sid: 0 for sid in stages}

    # BFS queue seeded with all nodes that have no predecessors.
    queue: deque[str] = deque(sid for sid, deg in in_degree.items() if deg == 0)

    while queue:
        current = queue.popleft()

        # Update all successors via the adjacency list — each edge visited once.
        for target in successors[current]:
            new_col = column[current] + 1
            if new_col > column[target]:
                column[target] = new_col
            in_degree[target] -= 1
            if in_degree[target] == 0:
                queue.append(target)

    # Detect cycles: any node with remaining in-degree was never dequeued.
    stuck = [sid for sid, deg in in_degree.items() if deg > 0]
    if stuck:
        logger.warning("Cycle detected in topology involving: %s", stuck)

    # Post-process: enforce source/sink placement using ALL connections
    # (including non-layout ones like writes/stores). A node that only has
    # outgoing connections is a source (column 0). A node that only has
    # incoming connections is a sink (last column).
    max_col = max(column.values(), default=0)

    all_outgoing: dict[str, bool] = {sid: False for sid in stages}
    all_incoming: dict[str, bool] = {sid: False for sid in stages}
    for conn in connections:
        if conn.from_id in stages:
            all_outgoing[conn.from_id] = True
        if conn.to_id in stages:
            all_incoming[conn.to_id] = True

    for sid, stage in stages.items():
        # Skip transport nodes (queues, exchanges) — they're positioned
        # by their connected services, not by this source/sink rule.
        if stage.visual.nodeType == "transport":
            continue

        has_out = all_outgoing[sid]
        has_in = all_incoming[sid]
        if has_out and not has_in:
            # Source node — keep at column 0 (BFS default).
            pass
        elif has_in and not has_out:
            # Sink node — push to last column.
            column[sid] = max(column[sid], max_col)

    # Write computed columns back into the stage objects.
    for sid, col in column.items():
        stages[sid].column = col
