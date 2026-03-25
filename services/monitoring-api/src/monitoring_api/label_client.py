"""ClassificationLabelClient — reads and writes classification label definitions.

Follows the same pattern as ArticleClient: short-lived psycopg (v3) connections
per call, synchronous methods, returns dataclasses, returns None on failure.

Classification labels are stored in the classification_labels table and define
the candidate topic classes used by the zero-shot topic-tagger pipeline.
"""

import logging
from dataclasses import dataclass

import psycopg

logger = logging.getLogger(__name__)


@dataclass
class ClassificationLabel:
    id: int
    name: str
    description: str
    color: str
    enabled: bool
    created_at: str


class ClassificationLabelClient:
    """Reads and writes classification label definitions.

    Uses a short-lived connection per call (same rationale as ArticleClient).
    All methods are synchronous — FastAPI endpoints run them in a thread pool
    executor to avoid blocking the event loop.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def get_labels(self) -> list[ClassificationLabel] | None:
        """Fetch all classification labels ordered by name.

        Returns None if the database is unreachable.
        """
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, name, description, color, enabled, created_at
                        FROM classification_labels
                        ORDER BY name
                        """
                    )
                    rows = cur.fetchall()

            return [
                ClassificationLabel(
                    id=row[0],
                    name=row[1],
                    description=row[2],
                    color=row[3],
                    enabled=row[4],
                    created_at=(
                        row[5].isoformat() if hasattr(row[5], "isoformat") else str(row[5])
                    ),
                )
                for row in rows
            ]
        except Exception as exc:
            logger.warning("get_labels failed: %s", exc)
            return None

    def create_label(self, name: str, description: str, color: str) -> ClassificationLabel | None:
        """Insert a new classification label.

        Returns the created label, or None if the insert failed (e.g. duplicate name).
        """
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO classification_labels (name, description, color)
                        VALUES (%s, %s, %s)
                        RETURNING id, name, description, color, enabled, created_at
                        """,
                        (name, description, color),
                    )
                    row = cur.fetchone()
                conn.commit()

            if row is None:
                return None

            return ClassificationLabel(
                id=row[0],
                name=row[1],
                description=row[2],
                color=row[3],
                enabled=row[4],
                created_at=(row[5].isoformat() if hasattr(row[5], "isoformat") else str(row[5])),
            )
        except Exception as exc:
            logger.warning("create_label failed for '%s': %s", name, exc)
            return None

    def update_label(
        self,
        label_id: int,
        description: str | None = None,
        color: str | None = None,
        enabled: bool | None = None,
    ) -> ClassificationLabel | None:
        """Update one or more fields of an existing label.

        Only the fields that are not None will be updated. Returns the updated
        label, or None if no row matched label_id or the update failed.

        We build the SET clause dynamically from whitelisted column names so
        there's no risk of SQL injection from the field names.
        """
        # Build a list of (column, value) pairs for the fields to update.
        updates: list[tuple[str, object]] = []
        if description is not None:
            updates.append(("description", description))
        if color is not None:
            updates.append(("color", color))
        if enabled is not None:
            updates.append(("enabled", enabled))

        if not updates:
            # Nothing to update — fetch and return the current state.
            labels = self.get_labels()
            if labels is None:
                return None
            return next((lbl for lbl in labels if lbl.id == label_id), None)

        try:
            # Build: "description = %s, color = %s" — columns are whitelisted above.
            set_clause = ", ".join(f"{col} = %s" for col, _ in updates)
            values = [val for _, val in updates]
            values.append(label_id)

            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        UPDATE classification_labels
                        SET {set_clause}
                        WHERE id = %s
                        RETURNING id, name, description, color, enabled, created_at
                        """,
                        values,
                    )
                    row = cur.fetchone()
                conn.commit()

            if row is None:
                return None

            return ClassificationLabel(
                id=row[0],
                name=row[1],
                description=row[2],
                color=row[3],
                enabled=row[4],
                created_at=(row[5].isoformat() if hasattr(row[5], "isoformat") else str(row[5])),
            )
        except Exception as exc:
            logger.warning("update_label failed for id %s: %s", label_id, exc)
            return None

    def delete_label(self, label_id: int) -> bool:
        """Delete a classification label by id.

        Returns True if a row was deleted, False if no row matched label_id.
        """
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM classification_labels WHERE id = %s",
                        (label_id,),
                    )
                    deleted = cur.rowcount > 0
                conn.commit()
            return deleted
        except Exception as exc:
            logger.warning("delete_label failed for id %s: %s", label_id, exc)
            return False
