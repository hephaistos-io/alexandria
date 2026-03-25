"""Import topic labels from Markdown files back into PostgreSQL.

Reads the YAML frontmatter of each ``.md`` file in the input directory,
extracts ``id`` and ``topic_label``, and updates the corresponding row.
Files with an empty ``topic_label`` are skipped.

Usage:
    python import_labels.py --input ./labelling/
"""

from __future__ import annotations

import argparse
import os
import re
import sys

import psycopg

# No default — DATABASE_URL must be set explicitly, matching the main service.
# For local dev: export DATABASE_URL="postgresql://alexandria:alexandria@localhost:5432/alexandria"

# Matches the YAML frontmatter block between --- markers.
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def parse_frontmatter(text: str) -> dict[str, str]:
    """Extract key-value pairs from YAML frontmatter.

    Uses simple line-by-line parsing rather than a YAML library — the
    frontmatter is flat (no nesting) so a full parser isn't needed.
    """
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}

    result: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        result[key.strip()] = value.strip()
    return result


def import_labels(database_url: str, input_dir: str) -> None:
    md_files = sorted(f for f in os.listdir(input_dir) if f.endswith(".md"))

    if not md_files:
        print(f"No .md files found in {input_dir}")
        return

    updated = 0
    skipped = 0
    errors = 0

    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        for filename in md_files:
            filepath = os.path.join(input_dir, filename)
            with open(filepath, encoding="utf-8") as f:
                content = f.read()

            meta = parse_frontmatter(content)
            article_id = meta.get("id", "")
            labels_raw = meta.get("manual_labels", "")

            if not article_id:
                print(f"  SKIP {filename}: no id in frontmatter")
                errors += 1
                continue

            if not labels_raw:
                skipped += 1
                continue

            # Parse comma-separated labels, e.g. "POLITICS, FINANCIAL" → ["POLITICS", "FINANCIAL"]
            labels = [
                part.strip()
                for part in labels_raw.split(",")
                if part.strip()
            ]

            if len(labels) > 3:
                print(f"  WARN {filename}: more than 3 labels, truncating to first 3")
                labels = labels[:3]

            try:
                cur.execute(
                    "UPDATE articles SET manual_labels = %s,"
                    " manual_labelled_at = now() WHERE id = %s",
                    (labels, int(article_id)),
                )
                if cur.rowcount > 0:
                    updated += 1
                else:
                    print(f"  WARN {filename}: article id={article_id} not found in DB")
                    errors += 1
            except Exception as exc:
                print(f"  ERROR {filename}: {exc}")
                errors += 1

        conn.commit()

    print(f"Updated {updated} labels, skipped {skipped} empty, {errors} errors.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import topic labels from Markdown files")
    parser.add_argument("--input", required=True, help="Directory containing labelled .md files")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is required")
        sys.exit(1)
    import_labels(database_url, args.input)


if __name__ == "__main__":
    main()
