"""RelationTypeClient — reads and writes relation type definitions.

Same pattern as EntityRoleTypeClient: short-lived psycopg (v3) connections
per call, synchronous methods, returns dataclasses, returns None on failure.

Relation types define the kinds of directed or undirected relationships that
can exist between entities in the temporal knowledge graph (e.g. ALLY_OF,
FUNDS, CONTROLS).
"""

import logging
from dataclasses import dataclass

import psycopg

logger = logging.getLogger(__name__)


@dataclass
class RelationType:
    id: int
    name: str
    description: str
    color: str
    directed: bool
    enabled: bool
    created_at: str


class RelationTypeClient:
    """Reads and writes relation type definitions.

    Uses a short-lived connection per call (same rationale as EntityRoleTypeClient).
    All methods are synchronous — FastAPI endpoints run them in a thread pool
    executor to avoid blocking the event loop.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def get_relation_types(self) -> list[RelationType] | None:
        """Fetch all relation types ordered by name.

        Returns None if the database is unreachable.
        """
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, name, description, color, directed, enabled, created_at
                        FROM relation_types
                        ORDER BY name
                        """
                    )
                    rows = cur.fetchall()

            return [
                RelationType(
                    id=row[0],
                    name=row[1],
                    description=row[2],
                    color=row[3],
                    directed=row[4],
                    enabled=row[5],
                    created_at=(
                        row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6])
                    ),
                )
                for row in rows
            ]
        except Exception as exc:
            logger.warning("get_relation_types failed: %s", exc)
            return None

    def create_relation_type(
        self, name: str, description: str, color: str, directed: bool = True
    ) -> RelationType | None:
        """Insert a new relation type.

        Returns the created relation type, or None if the insert failed
        (e.g. duplicate name).
        """
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO relation_types (name, description, color, directed)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id, name, description, color, directed, enabled, created_at
                        """,
                        (name, description, color, directed),
                    )
                    row = cur.fetchone()
                conn.commit()

            if row is None:
                return None

            return RelationType(
                id=row[0],
                name=row[1],
                description=row[2],
                color=row[3],
                directed=row[4],
                enabled=row[5],
                created_at=(row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6])),
            )
        except Exception as exc:
            logger.warning("create_relation_type failed for '%s': %s", name, exc)
            return None

    def update_relation_type(
        self,
        relation_type_id: int,
        description: str | None = None,
        color: str | None = None,
        directed: bool | None = None,
        enabled: bool | None = None,
    ) -> RelationType | None:
        """Update one or more fields of an existing relation type.

        Only the fields that are not None will be updated. Returns the updated
        relation type, or None if no row matched relation_type_id or the update failed.

        We build the SET clause dynamically from whitelisted column names so
        there's no risk of SQL injection from the field names.
        """
        # Build a list of (column, value) pairs for the fields to update.
        updates: list[tuple[str, object]] = []
        if description is not None:
            updates.append(("description", description))
        if color is not None:
            updates.append(("color", color))
        if directed is not None:
            updates.append(("directed", directed))
        if enabled is not None:
            updates.append(("enabled", enabled))

        if not updates:
            # Nothing to update — fetch and return the current state.
            relation_types = self.get_relation_types()
            if relation_types is None:
                return None
            return next((rt for rt in relation_types if rt.id == relation_type_id), None)

        try:
            # Build: "description = %s, color = %s" — columns are whitelisted above.
            set_clause = ", ".join(f"{col} = %s" for col, _ in updates)
            values = [val for _, val in updates]
            values.append(relation_type_id)

            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        UPDATE relation_types
                        SET {set_clause}
                        WHERE id = %s
                        RETURNING id, name, description, color, directed, enabled, created_at
                        """,
                        values,
                    )
                    row = cur.fetchone()
                conn.commit()

            if row is None:
                return None

            return RelationType(
                id=row[0],
                name=row[1],
                description=row[2],
                color=row[3],
                directed=row[4],
                enabled=row[5],
                created_at=(row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6])),
            )
        except Exception as exc:
            logger.warning(
                "update_relation_type failed for id %s: %s", relation_type_id, exc
            )
            return None

    def delete_relation_type(self, relation_type_id: int) -> bool:
        """Delete a relation type by id.

        Returns True if a row was deleted, False if no row matched relation_type_id.
        """
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM relation_types WHERE id = %s",
                        (relation_type_id,),
                    )
                    deleted = cur.rowcount > 0
                conn.commit()
            return deleted
        except Exception as exc:
            logger.warning(
                "delete_relation_type failed for id %s: %s", relation_type_id, exc
            )
            return False
