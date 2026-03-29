"""Load entity role type definitions from the database.

Fetches only enabled role types so that disabled types are excluded from
inference automatically — no service restart required.

Each role type has a name (stored on the entity when matched) and a description
(fed to the zero-shot model as the NLI hypothesis).
"""

import logging
from dataclasses import dataclass

import psycopg

logger = logging.getLogger(__name__)


@dataclass
class LabelDefinition:
    """A classification label with its description for the zero-shot model."""
    name: str
    description: str


def load_role_types(database_url: str) -> list[LabelDefinition]:
    """Fetch all enabled entity role types (name + description) from the DB.

    Returns an empty list if the DB is unreachable or no role types exist.
    The caller (main) logs a warning in that case and retries on the
    next scheduled refresh.

    We need both fields: the description is what gets fed to the zero-shot
    model as the NLI hypothesis (e.g. "a source of the conflict described"),
    and the name is what we store on the entity (e.g. "ACTOR").
    """
    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name, description"
                    " FROM entity_role_types WHERE enabled = true ORDER BY name"
                )
                rows = cur.fetchall()
        role_types = [LabelDefinition(name=row[0], description=row[1]) for row in rows]
        logger.debug("Loaded %d entity role types from DB", len(role_types))
        return role_types
    except Exception as exc:
        logger.warning("Failed to load entity role types: %s", exc)
        return []
