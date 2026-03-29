"""GraphClient — queries Neo4j for the temporal relation graph.

Temporal decay is computed in Python, not Cypher, because Neo4j Community
Edition may not have the exp() math function. The formula is:

    display_strength = base_strength * article_count^α * exp(-lambda * hours_since_last_seen)

This is the standard exponential decay model. Lambda controls the "half-life":
  - A small lambda (e.g. 0.001) means relations fade slowly (~29-day half-life)
  - A large lambda (e.g. 0.1) means relations fade quickly (~7-hour half-life)

The half-life formula is: t_half = ln(2) / lambda ≈ 0.693 / lambda
"""

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone

import neo4j

logger = logging.getLogger(__name__)

# Fetches all RELATION edges with both endpoint entities. The ORDER BY in
# Cypher is an optimistic hint — Python re-sorts after applying decay anyway.
FETCH_ALL_QUERY = """
MATCH (a:Entity)-[r:RELATION]->(b:Entity)
RETURN a.qid AS source_qid, a.name AS source_name, a.entity_type AS source_type,
       b.qid AS target_qid, b.name AS target_name, b.entity_type AS target_type,
       r.relation_type AS relation_type, r.base_strength AS base_strength,
       r.last_seen AS last_seen, r.first_seen AS first_seen,
       r.article_count AS article_count
ORDER BY r.base_strength DESC
"""


@dataclass
class GraphResult:
    nodes: list[dict]
    edges: list[dict]


class GraphClient:
    """Queries the Neo4j temporal relation graph with decay applied in Python.

    The driver is long-lived (created once at startup, closed at shutdown).
    Each call to get_graph() opens a short-lived session from the driver's
    internal connection pool — this is the standard neo4j driver pattern.

    All methods are synchronous — FastAPI endpoints run them via run_in_executor.
    """

    def __init__(self, uri: str, auth: tuple[str, str]) -> None:
        self._driver = neo4j.GraphDatabase.driver(uri, auth=auth)

    def get_graph(
        self,
        lambda_decay: float = 0.01,
        min_strength: float = 0.1,
        corroboration: float = 0.5,
        relation_types: list[str] | None = None,
        limit: int = 200,
    ) -> dict:
        """Query the graph and apply temporal decay to edge strengths.

        Args:
            lambda_decay: Decay rate (higher = faster fade). See module docstring.
            min_strength: Edges with display_strength below this are excluded.
            corroboration: Exponent (α) for article_count weighting. The formula
                becomes: display = base * count^α * exp(-λ * hours). At α=0 the
                count is ignored (count^0 = 1). At α=0.5 (default), 4 articles
                give a 2x boost, 9 articles a 3x boost (square root scaling).
                At α=1, the boost is linear with article count.
            relation_types: If provided, only edges with these relation_type
                values are included. Pass None to include all types.
            limit: Maximum number of edges to return (applied after filtering
                and sorting by display_strength descending).

        Returns:
            {"nodes": [...], "edges": [...]} where nodes are deduplicated
            entity dicts and edges carry both base_strength and display_strength.
        """
        try:
            with self._driver.session() as session:
                result = session.run(FETCH_ALL_QUERY)
                records = list(result)
        except Exception as exc:
            logger.warning("get_graph Neo4j query failed: %s", exc)
            return {"nodes": [], "edges": []}

        now = datetime.now(timezone.utc)
        edges = []
        nodes_by_qid: dict[str, dict] = {}

        for record in records:
            # --- Temporal decay ---
            # The neo4j driver returns datetimes as neo4j.time.DateTime objects.
            # .to_native() converts them to stdlib datetime.datetime instances.
            last_seen = record["last_seen"]
            if hasattr(last_seen, "to_native"):
                last_seen_dt = last_seen.to_native()
            else:
                last_seen_dt = last_seen

            # Ensure the datetime is timezone-aware before subtracting.
            if last_seen_dt.tzinfo is None:
                last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)

            hours_elapsed = (now - last_seen_dt).total_seconds() / 3600
            base: float = record["base_strength"] or 0.0
            count: int = record["article_count"] or 1
            # Corroboration boost: count^α. At α=0.5 (default), 4 articles = 2x,
            # 9 articles = 3x. Single-mention edges get no boost (1^α = 1).
            display = base * (count**corroboration) * math.exp(-lambda_decay * hours_elapsed)

            if display < min_strength:
                continue

            rel_type: str = record["relation_type"]
            if relation_types is not None and rel_type not in relation_types:
                continue

            # --- Collect nodes (deduplicated by qid) ---
            for prefix in ("source", "target"):
                qid: str = record[f"{prefix}_qid"]
                if qid not in nodes_by_qid:
                    nodes_by_qid[qid] = {
                        "qid": qid,
                        "name": record[f"{prefix}_name"],
                        "entity_type": record[f"{prefix}_type"],
                    }

            # --- Convert first_seen ---
            first_seen = record["first_seen"]
            if hasattr(first_seen, "to_native"):
                first_seen_dt = first_seen.to_native()
            else:
                first_seen_dt = first_seen

            if first_seen_dt.tzinfo is None:
                first_seen_dt = first_seen_dt.replace(tzinfo=timezone.utc)

            edges.append(
                {
                    "source": record["source_qid"],
                    "target": record["target_qid"],
                    "relation_type": rel_type,
                    "display_strength": round(display, 4),
                    "base_strength": round(base, 4),
                    "last_seen": last_seen_dt.isoformat(),
                    "first_seen": first_seen_dt.isoformat(),
                    "article_count": record["article_count"],
                }
            )

        # Sort by display_strength descending and apply the limit.
        edges.sort(key=lambda e: e["display_strength"], reverse=True)
        edges = edges[:limit]

        # Only return nodes that appear in the surviving (post-filter) edges.
        edge_qids: set[str] = set()
        for e in edges:
            edge_qids.add(e["source"])
            edge_qids.add(e["target"])

        nodes = [n for qid, n in nodes_by_qid.items() if qid in edge_qids]

        return {"nodes": nodes, "edges": edges}

    def close(self) -> None:
        """Close the underlying Neo4j driver and release its connection pool."""
        self._driver.close()
