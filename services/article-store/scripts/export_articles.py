"""Export articles from PostgreSQL as Markdown files for manual topic labelling.

Each file contains YAML frontmatter (id, origin, url, published, topic_label)
followed by the article title and full content.  Fill in ``topic_label`` and
run ``import_labels.py`` to write the labels back.

Usage:
    python export_articles.py --output ./labelling/
    python export_articles.py --output ./labelling/ --all
"""

from __future__ import annotations

import argparse
import os
import re
import sys

import psycopg

# No default — DATABASE_URL must be set explicitly, matching the main service.
# For local dev: export DATABASE_URL="postgresql://alexandria:alexandria@localhost:5432/alexandria"


def slugify(text: str, max_length: int = 60) -> str:
    """Turn a title into a filesystem-safe slug."""
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:max_length].rstrip("-")


def export(database_url: str, output_dir: str, *, include_labelled: bool = False) -> None:
    os.makedirs(output_dir, exist_ok=True)

    query = "SELECT id, origin, url, published_at, manual_labels, title, content FROM articles"
    if not include_labelled:
        query += " WHERE manual_labels IS NULL"
    query += " ORDER BY id"

    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()

    if not rows:
        print("No articles to export.")
        return

    written = 0
    for row in rows:
        article_id, origin, url, published_at, manual_labels, title, content = row

        published_str = published_at.isoformat() if published_at else ""
        labels_str = ", ".join(manual_labels) if manual_labels else ""
        slug = slugify(title)
        filename = f"{article_id:04d}_{slug}.md"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("---\n")
            f.write(f"id: {article_id}\n")
            f.write(f"origin: {origin}\n")
            f.write(f"url: {url}\n")
            f.write(f"published: {published_str}\n")
            f.write(f"manual_labels: {labels_str}\n")
            f.write("---\n\n")
            f.write(f"# {title}\n\n")
            f.write(content)
            f.write("\n")

        written += 1

    print(f"Exported {written} articles to {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export articles for labelling")
    parser.add_argument("--output", required=True, help="Output directory for Markdown files")
    parser.add_argument(
        "--all",
        action="store_true",
        dest="include_labelled",
        help="Include already-labelled articles (default: unlabelled only)",
    )
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is required")
        sys.exit(1)
    export(database_url, args.output, include_labelled=args.include_labelled)


if __name__ == "__main__":
    main()
