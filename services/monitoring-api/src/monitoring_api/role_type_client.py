"""EntityRoleTypeClient — reads and writes entity role type definitions.

Follows the same pattern as ClassificationLabelClient: short-lived psycopg (v3)
connections per call, synchronous methods, returns dataclasses, returns None on
failure.

Entity role types are stored in the entity_role_types table and define the
candidate roles used to annotate which role each detected entity plays in an
article (e.g. AFFECTED, SOURCE, ACTOR).
"""

import logging
from dataclasses import dataclass

import psycopg

logger = logging.getLogger(__name__)


@dataclass
class EntityRoleType:
    id: int
    name: str
    description: str
    color: str
    enabled: bool
    created_at: str


class EntityRoleTypeClient:
    """Reads and writes entity role type definitions.

    Uses a short-lived connection per call (same rationale as ArticleClient).
    All methods are synchronous — FastAPI endpoints run them in a thread pool
    executor to avoid blocking the event loop.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def get_role_types(self) -> list[EntityRoleType] | None:
        """Fetch all entity role types ordered by name.

        Returns None if the database is unreachable.
        """
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, name, description, color, enabled, created_at
                        FROM entity_role_types
                        ORDER BY name
                        """
                    )
                    rows = cur.fetchall()

            return [
                EntityRoleType(
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
            logger.warning("get_role_types failed: %s", exc)
            return None

    def create_role_type(
        self, name: str, description: str, color: str
    ) -> EntityRoleType | None:
        """Insert a new entity role type.

        Returns the created role type, or None if the insert failed (e.g. duplicate name).
        """
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO entity_role_types (name, description, color)
                        VALUES (%s, %s, %s)
                        RETURNING id, name, description, color, enabled, created_at
                        """,
                        (name, description, color),
                    )
                    row = cur.fetchone()
                conn.commit()

            if row is None:
                return None

            return EntityRoleType(
                id=row[0],
                name=row[1],
                description=row[2],
                color=row[3],
                enabled=row[4],
                created_at=(row[5].isoformat() if hasattr(row[5], "isoformat") else str(row[5])),
            )
        except Exception as exc:
            logger.warning("create_role_type failed for '%s': %s", name, exc)
            return None

    def update_role_type(
        self,
        role_type_id: int,
        description: str | None = None,
        color: str | None = None,
        enabled: bool | None = None,
    ) -> EntityRoleType | None:
        """Update one or more fields of an existing role type.

        Only the fields that are not None will be updated. Returns the updated
        role type, or None if no row matched role_type_id or the update failed.

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
            role_types = self.get_role_types()
            if role_types is None:
                return None
            return next((rt for rt in role_types if rt.id == role_type_id), None)

        try:
            # Build: "description = %s, color = %s" — columns are whitelisted above.
            set_clause = ", ".join(f"{col} = %s" for col, _ in updates)
            values = [val for _, val in updates]
            values.append(role_type_id)

            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        UPDATE entity_role_types
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

            return EntityRoleType(
                id=row[0],
                name=row[1],
                description=row[2],
                color=row[3],
                enabled=row[4],
                created_at=(row[5].isoformat() if hasattr(row[5], "isoformat") else str(row[5])),
            )
        except Exception as exc:
            logger.warning("update_role_type failed for id %s: %s", role_type_id, exc)
            return None

    def delete_role_type(self, role_type_id: int) -> bool:
        """Delete an entity role type by id.

        Returns True if a row was deleted, False if no row matched role_type_id.
        """
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM entity_role_types WHERE id = %s",
                        (role_type_id,),
                    )
                    deleted = cur.rowcount > 0
                conn.commit()
            return deleted
        except Exception as exc:
            logger.warning("delete_role_type failed for id %s: %s", role_type_id, exc)
            return False
