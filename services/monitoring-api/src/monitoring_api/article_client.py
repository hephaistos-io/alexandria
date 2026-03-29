"""ArticleClient — reads and writes article data for the labelling feature.

Follows the same pattern as DbClient: short-lived psycopg (v3) connections
per call, synchronous methods (callers in server.py wrap in run_in_executor),
returns dataclasses, catches exceptions and returns None on failure.

MAX_LABELS limits how many labels can be applied to a single article.

Column naming:
  manual_labels / manual_labelled_at  — set by human annotators in the UI
  automatic_labels / classified_at    — set by the topic-tagger pipeline
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg

logger = logging.getLogger(__name__)

MAX_LABELS = 3

# Whitelisted filter clauses — maps a user-facing filter name to a SQL fragment.
# Using a dict of trusted SQL fragments (rather than string interpolation) prevents
# SQL injection. The user's input is only used as a dict key, never inserted into SQL.
_FILTER_CLAUSES: dict[str, str] = {
    "all": "",
    "labelled": "WHERE manual_labels IS NOT NULL",
    "unlabelled": "WHERE manual_labels IS NULL",
    "auto_labelled": "WHERE automatic_labels IS NOT NULL",
}

# Whitelisted sort columns — maps user-facing names to actual column names.
# Same principle: user input selects from a fixed set, never touches SQL directly.
_SORT_COLUMNS: dict[str, str] = {
    "date_ingested": "created_at",
    "source_origin": "origin",
}

# Attribution filter clauses — all variants require entities IS NOT NULL as a
# base condition (we only show articles that have entities to annotate).
# The additional clause is joined with AND where needed.
_ATTRIBUTION_FILTER_CLAUSES: dict[str, str] = {
    # Show all articles that have entities (base condition only).
    "all": "WHERE entities IS NOT NULL",
    # Annotated: have entities AND the human has already assigned roles.
    "annotated": "WHERE entities IS NOT NULL AND manual_entity_roles IS NOT NULL",
    # Unannotated: have entities but no human annotation yet.
    "unannotated": "WHERE entities IS NOT NULL AND manual_entity_roles IS NULL",
    # auto_classified: entities already carry an auto-assigned role field.
    # For now this is the same as "all" — the column used for auto roles
    # is embedded in the entities JSONB, not a separate column.
    "auto_classified": "WHERE entities IS NOT NULL",
}


@dataclass
class LabellingStats:
    total_count: int
    labelled_count: int
    unlabelled_count: int
    progress_percent: float
    classified_count: int


@dataclass
class ArticleSummary:
    id: int
    origin: str
    title: str
    created_at: str
    manual_labels: list[str] | None
    automatic_labels: list[str] | None


@dataclass
class ArticlePage:
    articles: list[ArticleSummary]
    total: int
    page: int
    page_size: int


@dataclass
class ArchiveArticle:
    id: int
    origin: str
    title: str
    summary: str | None
    published_at: str | None
    created_at: str
    manual_labels: list[str] | None
    automatic_labels: list[str] | None


@dataclass
class ArchivePage:
    articles: list[ArchiveArticle]
    total: int
    page: int
    page_size: int


@dataclass
class ArticleDetail:
    id: int
    url: str
    source: str
    origin: str
    title: str
    summary: str | None
    content: str
    published_at: str | None
    created_at: str
    fetched_at: str
    scraped_at: str
    manual_labels: list[str] | None
    automatic_labels: list[str] | None
    entities: list[dict] | None


@dataclass
class AttributionStats:
    total_with_entities: int
    annotated_count: int
    unannotated_count: int
    progress_percent: float


@dataclass
class AttributionArticleSummary:
    id: int
    origin: str
    title: str
    summary: str | None
    content: str
    created_at: str
    entities: list[dict] | None
    manual_entity_roles: dict | None
    entity_roles_labelled_at: str | None


@dataclass
class AttributionArticlePage:
    articles: list[AttributionArticleSummary]
    total: int
    page: int
    page_size: int


@dataclass
class DashboardArticle:
    id: int
    url: str
    source: str
    origin: str
    title: str
    summary: str | None
    published_at: str | None
    created_at: str
    manual_labels: list[str] | None
    automatic_labels: list[str] | None
    entities: list[dict] | None


class ArticleClient:
    """Reads and writes article data for the labelling workflow.

    Uses a short-lived connection per call (same rationale as DbClient).
    All methods are synchronous — the FastAPI endpoints run them in a
    thread pool executor to avoid blocking the event loop.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def get_labelling_stats(self) -> LabellingStats | None:
        """Query total, labelled, unlabelled, and auto-classified article counts.

        Returns None if the database is unreachable.
        """
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            COUNT(*),
                            COUNT(*) FILTER (WHERE manual_labels IS NOT NULL),
                            COUNT(*) FILTER (WHERE manual_labels IS NULL),
                            COUNT(*) FILTER (WHERE automatic_labels IS NOT NULL)
                        FROM articles
                        """
                    )
                    row = cur.fetchone()

            if row is None:
                return LabellingStats(
                    total_count=0,
                    labelled_count=0,
                    unlabelled_count=0,
                    progress_percent=0.0,
                    classified_count=0,
                )

            total, labelled, unlabelled, classified = (
                int(row[0]),
                int(row[1]),
                int(row[2]),
                int(row[3]),
            )
            progress = (labelled / total * 100.0) if total > 0 else 0.0

            return LabellingStats(
                total_count=total,
                labelled_count=labelled,
                unlabelled_count=unlabelled,
                progress_percent=round(progress, 2),
                classified_count=classified,
            )
        except Exception as exc:
            logger.warning("Labelling stats query failed: %s", exc)
            return None

    def get_articles(
        self,
        page: int,
        page_size: int,
        filter_: str,
        sort_by: str,
        sort_dir: str,
    ) -> ArticlePage | None:
        """Fetch a page of articles with optional filtering and sorting.

        Uses two queries in one connection: a COUNT for total rows, then the
        actual data query with LIMIT/OFFSET for pagination.

        Returns None if the database is unreachable.
        """
        where_clause = _FILTER_CLAUSES.get(filter_, "")
        sort_column = _SORT_COLUMNS.get(sort_by, "created_at")
        # sort_dir is already validated by the caller, but defend in depth
        direction = "ASC" if sort_dir == "asc" else "DESC"
        offset = (page - 1) * page_size

        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    # Query 1: total count (with filter applied)
                    count_sql = f"SELECT COUNT(*) FROM articles {where_clause}"
                    cur.execute(count_sql)
                    count_row = cur.fetchone()
                    total = int(count_row[0]) if count_row else 0

                    # Query 2: paginated data
                    # We build SQL from whitelisted fragments only — no user input
                    # is interpolated into the query string. The LIMIT and OFFSET
                    # values go through psycopg's parameter binding (%s), which
                    # handles escaping and type safety.
                    data_sql = f"""
                        SELECT id, origin, title, created_at, manual_labels, automatic_labels
                        FROM articles
                        {where_clause}
                        ORDER BY {sort_column} {direction}
                        LIMIT %s OFFSET %s
                    """
                    cur.execute(data_sql, (page_size, offset))
                    rows = cur.fetchall()

            articles = []
            for row in rows:
                article_id, origin, title, created_at, manual_labels, automatic_labels = row
                # Format datetime as ISO string for JSON serialisation
                created_str = (
                    created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
                )
                articles.append(
                    ArticleSummary(
                        id=int(article_id),
                        origin=str(origin),
                        title=str(title),
                        created_at=created_str,
                        manual_labels=manual_labels,
                        automatic_labels=automatic_labels,
                    )
                )

            return ArticlePage(
                articles=articles,
                total=total,
                page=page,
                page_size=page_size,
            )
        except Exception as exc:
            logger.warning("Articles query failed: %s", exc)
            return None

    def update_labels(self, article_id: int, labels: list[str]) -> bool:
        """Update the manual_labels for a single article.

        If labels is an empty list, both manual_labels and manual_labelled_at are
        set to NULL (clearing the labels).

        Returns True if the article was found and updated, False if no row
        matched the given article_id.
        """
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    if labels:
                        cur.execute(
                            "UPDATE articles SET manual_labels = %s, manual_labelled_at = now() "
                            "WHERE id = %s",
                            (labels, article_id),
                        )
                    else:
                        cur.execute(
                            "UPDATE articles SET manual_labels = NULL, manual_labelled_at = NULL "
                            "WHERE id = %s",
                            (article_id,),
                        )
                    # rowcount tells us how many rows the UPDATE affected.
                    # If 0, the article_id didn't match any row.
                    updated = cur.rowcount > 0
                conn.commit()
            return updated
        except Exception as exc:
            logger.warning("Update labels failed for article %s: %s", article_id, exc)
            return False

    def get_dashboard_articles(self, since: str) -> list[DashboardArticle] | None:
        """Fetch classified articles published/created since the given timestamp.

        Only returns articles that have at least one automatic label (i.e.
        they've been through the topic-tagger). Unclassified articles show
        as #PENDING in the UI, which is noise for the live feed.

        `since` must be an ISO 8601 string, e.g. "2024-01-15T00:00:00Z".
        A safety cap of 2000 rows prevents runaway memory usage.

        Returns None if the database is unreachable.
        """
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, url, source, origin, title, summary, published_at,
                               created_at, manual_labels, automatic_labels, entities
                        FROM articles
                        WHERE automatic_labels IS NOT NULL
                          AND COALESCE(published_at, created_at) >= %s
                        ORDER BY COALESCE(published_at, created_at) DESC
                        LIMIT 2000
                        """,
                        (since,),
                    )
                    rows = cur.fetchall()

            results = []
            for row in rows:
                (
                    id_,
                    url,
                    source,
                    origin,
                    title,
                    summary,
                    published_at,
                    created_at,
                    manual_labels,
                    automatic_labels,
                    entities,
                ) = row
                results.append(
                    DashboardArticle(
                        id=int(id_),
                        url=str(url),
                        source=str(source),
                        origin=str(origin),
                        title=str(title),
                        summary=summary,
                        published_at=(
                            published_at.isoformat()
                            if hasattr(published_at, "isoformat")
                            else published_at
                        ),
                        created_at=(
                            created_at.isoformat()
                            if hasattr(created_at, "isoformat")
                            else str(created_at)
                        ),
                        manual_labels=manual_labels,
                        automatic_labels=automatic_labels,
                        entities=entities,
                    )
                )
            return results
        except Exception as exc:
            logger.warning("Dashboard articles query failed: %s", exc)
            return None

    def get_archive_articles(
        self,
        page: int,
        page_size: int,
        search: str,
        sort_dir: str,
    ) -> "ArchivePage | None":
        """Fetch a paginated list of articles for the Signal Archive.

        Supports optional full-text search on title (ILIKE) and sort direction.
        The search parameter is passed as a bound parameter — never interpolated
        into the SQL string — so it cannot cause SQL injection.

        Returns None if the database is unreachable.
        """
        # Validate sort direction defensively even though the caller already checks.
        direction = "ASC" if sort_dir == "asc" else "DESC"
        offset = (page - 1) * page_size

        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    if search:
                        # Parameterised ILIKE: the % wildcards are part of the
                        # value, not the SQL structure, so they are safe.
                        count_sql = "SELECT COUNT(*) FROM articles WHERE title ILIKE %s"
                        cur.execute(count_sql, (f"%{search}%",))
                    else:
                        cur.execute("SELECT COUNT(*) FROM articles")
                    count_row = cur.fetchone()
                    total = int(count_row[0]) if count_row else 0

                    if search:
                        data_sql = f"""
                            SELECT id, origin, title, summary, published_at, created_at,
                                   manual_labels, automatic_labels
                            FROM articles
                            WHERE title ILIKE %s
                            ORDER BY COALESCE(published_at, created_at) {direction}
                            LIMIT %s OFFSET %s
                        """
                        cur.execute(data_sql, (f"%{search}%", page_size, offset))
                    else:
                        data_sql = f"""
                            SELECT id, origin, title, summary, published_at, created_at,
                                   manual_labels, automatic_labels
                            FROM articles
                            ORDER BY COALESCE(published_at, created_at) {direction}
                            LIMIT %s OFFSET %s
                        """
                        cur.execute(data_sql, (page_size, offset))
                    rows = cur.fetchall()

            articles = []
            for row in rows:
                (
                    art_id,
                    origin,
                    title,
                    summary,
                    published_at,
                    created_at,
                    manual_labels,
                    automatic_labels,
                ) = row
                articles.append(
                    ArchiveArticle(
                        id=int(art_id),
                        origin=str(origin),
                        title=str(title),
                        summary=summary,
                        published_at=(
                            published_at.isoformat()
                            if hasattr(published_at, "isoformat")
                            else published_at
                        ),
                        created_at=(
                            created_at.isoformat()
                            if hasattr(created_at, "isoformat")
                            else str(created_at)
                        ),
                        manual_labels=manual_labels,
                        automatic_labels=automatic_labels,
                    )
                )

            return ArchivePage(
                articles=articles,
                total=total,
                page=page,
                page_size=page_size,
            )
        except Exception as exc:
            logger.warning("Archive articles query failed: %s", exc)
            return None

    def get_article_detail(self, article_id: int) -> "ArticleDetail | None":
        """Fetch the full detail for a single article by primary key.

        Returns None if no article with the given id exists, or if the
        database is unreachable.
        """
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, url, source, origin, title, summary, content,
                               published_at, created_at, fetched_at, scraped_at,
                               manual_labels, automatic_labels, entities
                        FROM articles
                        WHERE id = %s
                        """,
                        (article_id,),
                    )
                    row = cur.fetchone()

            if row is None:
                return None

            (
                id_,
                url,
                source,
                origin,
                title,
                summary,
                content,
                published_at,
                created_at,
                fetched_at,
                scraped_at,
                manual_labels,
                automatic_labels,
                entities,
            ) = row

            def _fmt(dt) -> str | None:
                if dt is None:
                    return None
                return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)

            return ArticleDetail(
                id=int(id_),
                url=str(url),
                source=str(source),
                origin=str(origin),
                title=str(title),
                summary=summary,
                content=str(content),
                published_at=_fmt(published_at),
                created_at=_fmt(created_at),
                fetched_at=_fmt(fetched_at),
                scraped_at=_fmt(scraped_at),
                manual_labels=manual_labels,
                automatic_labels=automatic_labels,
                entities=entities,
            )
        except Exception as exc:
            logger.warning("Article detail query failed for id %s: %s", article_id, exc)
            return None

    def delete_article(self, article_id: int) -> bool:
        """Delete a single article by primary key.

        Returns True if a row was deleted, False if no row matched or an
        error occurred. The caller is responsible for re-queuing the article
        before calling this — deletion is irreversible.
        """
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM articles WHERE id = %s", (article_id,))
                    deleted = cur.rowcount > 0
                conn.commit()
            return deleted
        except Exception as exc:
            logger.warning("Delete article failed for id %s: %s", article_id, exc)
            return False

    def get_attribution_stats(self) -> AttributionStats | None:
        """Query article counts needed for the attribution labelling progress bar.

        Only considers articles that have entities (articles without entities
        cannot be annotated at all). Returns None if the database is unreachable.
        """
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            COUNT(*) FILTER (WHERE entities IS NOT NULL),
                            COUNT(*) FILTER (WHERE manual_entity_roles IS NOT NULL),
                            COUNT(*) FILTER (
                                WHERE entities IS NOT NULL
                                AND manual_entity_roles IS NULL
                            )
                        FROM articles
                        """
                    )
                    row = cur.fetchone()

            if row is None:
                return AttributionStats(
                    total_with_entities=0,
                    annotated_count=0,
                    unannotated_count=0,
                    progress_percent=0.0,
                )

            total_with_entities, annotated, unannotated = (
                int(row[0]),
                int(row[1]),
                int(row[2]),
            )
            progress = (annotated / total_with_entities * 100.0) if total_with_entities > 0 else 0.0

            return AttributionStats(
                total_with_entities=total_with_entities,
                annotated_count=annotated,
                unannotated_count=unannotated,
                progress_percent=round(progress, 2),
            )
        except Exception as exc:
            logger.warning("Attribution stats query failed: %s", exc)
            return None

    def get_attribution_articles(
        self,
        page: int,
        page_size: int,
        filter_: str,
        sort_by: str,
        sort_dir: str,
    ) -> AttributionArticlePage | None:
        """Fetch a page of articles that have entities, with optional filtering.

        Uses two queries in one connection: a COUNT for total rows, then the
        actual data query with LIMIT/OFFSET for pagination.

        Only articles where entities IS NOT NULL are returned — these are the
        articles that have had entity resolution run and can be annotated.

        Returns None if the database is unreachable.
        """
        where_clause = _ATTRIBUTION_FILTER_CLAUSES.get(filter_, "WHERE entities IS NOT NULL")
        sort_column = _SORT_COLUMNS.get(sort_by, "created_at")
        # sort_dir is already validated by the caller, but defend in depth.
        direction = "ASC" if sort_dir == "asc" else "DESC"
        offset = (page - 1) * page_size

        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    # Query 1: total count (with filter applied)
                    count_sql = f"SELECT COUNT(*) FROM articles {where_clause}"
                    cur.execute(count_sql)
                    count_row = cur.fetchone()
                    total = int(count_row[0]) if count_row else 0

                    # Query 2: paginated data — only whitelisted SQL fragments
                    # are interpolated; LIMIT/OFFSET go through parameter binding.
                    data_sql = f"""
                        SELECT id, origin, title, summary, content, created_at,
                               entities, manual_entity_roles, entity_roles_labelled_at
                        FROM articles
                        {where_clause}
                        ORDER BY {sort_column} {direction}
                        LIMIT %s OFFSET %s
                    """
                    cur.execute(data_sql, (page_size, offset))
                    rows = cur.fetchall()

            articles = []
            for row in rows:
                (
                    article_id,
                    origin,
                    title,
                    summary,
                    content,
                    created_at,
                    entities,
                    manual_entity_roles,
                    entity_roles_labelled_at,
                ) = row
                created_str = (
                    created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
                )
                labelled_at_str = None
                if entity_roles_labelled_at is not None:
                    labelled_at_str = (
                        entity_roles_labelled_at.isoformat()
                        if hasattr(entity_roles_labelled_at, "isoformat")
                        else str(entity_roles_labelled_at)
                    )
                articles.append(
                    AttributionArticleSummary(
                        id=int(article_id),
                        origin=str(origin),
                        title=str(title),
                        summary=summary,
                        content=str(content),
                        created_at=created_str,
                        entities=entities,
                        manual_entity_roles=manual_entity_roles,
                        entity_roles_labelled_at=labelled_at_str,
                    )
                )

            return AttributionArticlePage(
                articles=articles,
                total=total,
                page=page,
                page_size=page_size,
            )
        except Exception as exc:
            logger.warning("Attribution articles query failed: %s", exc)
            return None

    def update_entity_roles(self, article_id: int, roles: dict) -> bool:
        """Update the manual_entity_roles for a single article.

        `roles` is a dict mapping Wikidata entity IDs to role names, e.g.:
            {"Q794": "TARGET", "Q30": "ACTOR"}

        If roles is an empty dict, both manual_entity_roles and
        entity_roles_labelled_at are set to NULL (clearing the annotation).

        Returns True if the article was found and updated, False if no row
        matched the given article_id or an error occurred.
        """
        try:
            import json as _json

            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    if roles:
                        cur.execute(
                            "UPDATE articles "
                            "SET manual_entity_roles = %s::jsonb, entity_roles_labelled_at = now() "
                            "WHERE id = %s",
                            (_json.dumps(roles), article_id),
                        )
                    else:
                        cur.execute(
                            "UPDATE articles "
                            "SET manual_entity_roles = NULL, entity_roles_labelled_at = NULL "
                            "WHERE id = %s",
                            (article_id,),
                        )
                    # rowcount > 0 means the article_id matched a row.
                    updated = cur.rowcount > 0
                conn.commit()
            return updated
        except Exception as exc:
            logger.warning("Update entity roles failed for article %s: %s", article_id, exc)
            return False

    def get_reparse_payloads(self) -> list[dict] | None:
        """Select every article for re-scraping (without deleting).

        Returns a list of dicts matching the ``articles.rss`` message
        format (the same shape the single-article reparse uses).

        The caller is responsible for publishing the payloads to RabbitMQ
        and THEN calling ``delete_all_articles()`` — this ordering ensures
        no data is lost if the publish step fails.

        Returns None if the database is unreachable.
        """
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT source, origin, title, url,
                               COALESCE(summary, ''), published_at
                        FROM articles
                        ORDER BY id
                        """
                    )
                    rows = cur.fetchall()

            results: list[dict] = []
            for row in rows:
                source, origin, title, url, summary, published_at = row
                results.append(
                    {
                        "source": source,
                        "origin": origin,
                        "title": title,
                        "url": url,
                        "summary": summary,
                        "published": (
                            published_at.isoformat()
                            if hasattr(published_at, "isoformat")
                            else published_at
                        ),
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            return results
        except Exception as exc:
            logger.warning("Reparse payloads query failed: %s", exc)
            return None

    def delete_all_articles(self) -> bool:
        """Delete all article rows from the database.

        Returns True if the deletion succeeded, False on error.
        """
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM articles")
                conn.commit()
            return True
        except Exception as exc:
            logger.warning("Delete all articles failed: %s", exc)
            return False

    def get_unlabelled_jsonl(self) -> list[dict] | None:
        """Fetch all manually-unlabelled articles as a list of dicts for JSONL export.

        Datetimes are formatted as ISO 8601 strings so they serialise cleanly
        to JSON.

        Returns None if the database is unreachable.
        """
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, origin, title, summary, content, published_at, created_at
                        FROM articles
                        WHERE manual_labels IS NULL
                        ORDER BY id
                        """
                    )
                    rows = cur.fetchall()

            results = []
            for row in rows:
                art_id, origin, title, summary, content, published_at, created_at = row
                results.append(
                    {
                        "id": art_id,
                        "origin": origin,
                        "title": title,
                        "summary": summary,
                        "content": content,
                        "published_at": (
                            published_at.isoformat()
                            if hasattr(published_at, "isoformat")
                            else published_at
                        ),
                        "created_at": (
                            created_at.isoformat()
                            if hasattr(created_at, "isoformat")
                            else created_at
                        ),
                    }
                )

            return results
        except Exception as exc:
            logger.warning("Unlabelled JSONL export failed: %s", exc)
            return None
