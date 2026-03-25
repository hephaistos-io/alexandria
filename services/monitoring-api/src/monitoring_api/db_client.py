"""DbClient — reads article statistics from PostgreSQL.

We reuse the same psycopg (v3) pattern established in article-store.
This is a read-only client — it never writes to the database.

A single SQL query retrieves everything we need in one round-trip:
  COUNT(*)                          — total articles
  MAX(created_at)                   — most recent insert
  COUNT(*) FILTER (WHERE ...)       — labelled articles

FILTER is a SQL standard clause (PostgreSQL-specific in practice) that lets
you apply a WHERE condition to an aggregate without a subquery or CASE.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

import psycopg

logger = logging.getLogger(__name__)


@dataclass
class DbStats:
    article_count: int
    latest_insert: datetime | None
    labelled_count: int


class DbClient:
    """Reads article stats from PostgreSQL.

    Uses a short-lived connection per call rather than keeping a persistent
    connection open. The monitoring API is called infrequently (polling from a
    dashboard), so connection overhead is acceptable and avoids idle connection
    issues in production.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def get_stats(self) -> DbStats | None:
        """Query article counts and latest insert time.

        Returns None if the database is unreachable — the caller should
        handle this as a degraded state rather than an error.
        """
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            COUNT(*),
                            MAX(created_at),
                            COUNT(*) FILTER (WHERE manual_labels IS NOT NULL)
                        FROM articles
                        """
                    )
                    row = cur.fetchone()

            if row is None:
                return DbStats(article_count=0, latest_insert=None, labelled_count=0)

            article_count, latest_insert, labelled_count = row
            return DbStats(
                article_count=int(article_count),
                latest_insert=latest_insert,
                labelled_count=int(labelled_count),
            )
        except Exception as exc:
            logger.warning("PostgreSQL stats query failed: %s", exc)
            return None
