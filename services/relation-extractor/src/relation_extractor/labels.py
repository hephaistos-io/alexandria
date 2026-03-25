"""Load relation type definitions from the database.

Fetches only enabled relation types so that disabled types are excluded from
inference automatically — no service restart required.

Each relation type has a name (stored on the graph edge), a description
(fed to the zero-shot model as the NLI hypothesis text), and a directed flag
that controls whether edge direction is meaningful.
"""

import logging
from dataclasses import dataclass

import psycopg

logger = logging.getLogger(__name__)


@dataclass
class RelationDefinition:
    """A relation type with its NLI description and directionality."""
    name: str
    description: str
    directed: bool


def load_relation_types(database_url: str) -> list[RelationDefinition]:
    """Fetch all enabled relation types from the DB.

    Returns an empty list if the DB is unreachable or no relation types exist.
    The caller (main) logs a warning in that case and retries on the next
    scheduled refresh.

    We need all three fields: description is fed to the NLI model, name is
    stored on the Neo4j edge, and directed controls canonicalization logic
    (undirected edges are stored with the smaller QID as source so we don't
    create duplicate edges in both directions).
    """
    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name, description, directed"
                    " FROM relation_types WHERE enabled = true ORDER BY name"
                )
                rows = cur.fetchall()
        relation_types = [
            RelationDefinition(name=row[0], description=row[1], directed=row[2])
            for row in rows
        ]
        logger.debug("Loaded %d relation types from DB", len(relation_types))
        return relation_types
    except Exception as exc:
        logger.warning("Failed to load relation types: %s", exc)
        return []
