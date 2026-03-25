"""ArticleStore — persists scraped articles to PostgreSQL."""

import logging

import psycopg

from article_store.schema import apply_schema

logger = logging.getLogger(__name__)


class ArticleStore:
    """Writes articles to PostgreSQL, deduplicating by URL.

    psycopg (v3) uses a different import path than the older psycopg2:
      import psycopg          # v3 — what we use here
      import psycopg2         # v2 — legacy, different API

    The connection is opened once at construction and reused for the
    lifetime of the process. This is fine for a single-threaded consumer
    that processes one message at a time.
    """

    def __init__(self, database_url: str) -> None:
        logger.info("Connecting to PostgreSQL")
        self._conn = psycopg.connect(database_url)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create the articles table if it does not already exist."""
        apply_schema(self._conn)
        logger.info("Schema ready")

    _REQUIRED_FIELDS = ("url", "source", "origin", "title", "content", "fetched_at", "scraped_at")

    def save(self, article: dict) -> bool:
        """Insert an article, skipping duplicates by URL.

        Returns True if the row was inserted, False if a duplicate was skipped.

        ON CONFLICT (url) DO NOTHING means PostgreSQL silently ignores the
        INSERT when the URL already exists. cursor.rowcount tells us whether
        anything actually landed: 1 = inserted, 0 = duplicate.

        Raises ValueError if required fields are missing from the article dict.
        """
        missing = [f for f in self._REQUIRED_FIELDS if f not in article]
        if missing:
            raise ValueError(
                f"Article missing required fields {missing}: "
                f"{article.get('url', '<no url>')}"
            )

        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO articles (
                    url, source, origin, title, summary, content,
                    published_at, fetched_at, scraped_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (url) DO NOTHING
                """,
                (
                    article["url"],
                    article["source"],
                    article["origin"],
                    article["title"],
                    article.get("summary"),
                    article["content"],
                    # ScrapedArticle uses "published", not "published_at"
                    article.get("published"),
                    article["fetched_at"],
                    article["scraped_at"],
                ),
            )
            inserted = cur.rowcount > 0
        self._conn.commit()
        return inserted

    def close(self) -> None:
        """Close the PostgreSQL connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            logger.info("PostgreSQL connection closed")
