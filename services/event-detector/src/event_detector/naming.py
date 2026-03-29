"""Auto-naming for detected events.

Generates human-readable titles and URL-safe slugs from the entities
and topic labels in a cluster.
"""

import re
from collections import Counter


def generate_title(
    entity_qids: list[str],
    entity_names: dict[str, str],
    idf_scores: dict[str, float],
    article_labels: list[list[str] | None],
) -> str:
    """Generate a title from the top entities + dominant topic label.

    Strategy:
    1. Sort entities by IDF descending — most distinctive first.
    2. Take the top 3 canonical names.
    3. Find the most common automatic_label across cluster articles.
    4. Join: "Israel-Iran-Hezbollah Conflict"

    If no topic label is available, omit the suffix.
    """
    # Sort QIDs by IDF score so the most distinctive entities come first.
    sorted_qids = sorted(entity_qids, key=lambda q: idf_scores.get(q, 0.0), reverse=True)
    top_names = []
    for qid in sorted_qids:
        name = entity_names.get(qid)
        if name and name not in top_names:
            top_names.append(name)
        if len(top_names) >= 3:
            break

    if not top_names:
        return "Unnamed Event"

    # Find the dominant topic label across all articles in the cluster.
    label_counts: Counter[str] = Counter()
    for labels in article_labels:
        if labels:
            for label in labels:
                label_counts[label] += 1

    suffix = ""
    if label_counts:
        dominant = label_counts.most_common(1)[0][0]
        # Title-case the label: "CONFLICT" → "Conflict"
        suffix = " " + dominant.capitalize()

    return "-".join(top_names) + suffix


def slugify(title: str) -> str:
    """Convert a title to a URL-safe slug.

    "Israel-Iran-Hezbollah Conflict" → "israel-iran-hezbollah-conflict"
    """
    slug = title.lower()
    # Replace anything that isn't a letter, digit, or hyphen with a hyphen.
    slug = re.sub(r"[^a-z0-9-]+", "-", slug)
    # Collapse multiple hyphens and strip leading/trailing ones.
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug
