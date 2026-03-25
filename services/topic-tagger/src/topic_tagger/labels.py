"""Load classification label definitions from the database.

Fetches only enabled labels so that disabled labels are excluded from
inference automatically — no service restart required.

Each label has a name (stored in the DB when matched) and a description
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


def load_labels(database_url: str) -> list[LabelDefinition]:
    """Fetch all enabled classification labels (name + description) from the DB.

    Returns an empty list if the DB is unreachable or no labels exist.
    The caller (main) logs a warning in that case and retries on the
    next scheduled refresh.

    We need both fields: the description is what gets fed to the zero-shot
    model as the NLI hypothesis (e.g. "This text is about armed conflicts..."),
    and the name is what we store in automatic_labels (e.g. "CONFLICT").
    """
    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name, description"
                    " FROM classification_labels"
                    " WHERE enabled = true ORDER BY name"
                )
                rows = cur.fetchall()
        labels = [LabelDefinition(name=row[0], description=row[1]) for row in rows]
        logger.debug("Loaded %d classification labels from DB", len(labels))
        return labels
    except Exception as exc:
        logger.warning("Failed to load classification labels: %s", exc)
        return []
