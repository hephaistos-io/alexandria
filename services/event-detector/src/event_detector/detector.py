"""Core event detection logic.

Clusters articles by shared Wikidata entity QIDs, scores clusters with a
heat formula, and matches them to existing events or creates new ones.

The algorithm is entity-first: two articles are connected if they share
enough distinctive entities (measured by IDF).  Connected components of
this article graph form the candidate event clusters.

No ML dependencies — clustering is pure Python using collections and math.
"""

import logging
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone

from event_detector.models import ArticleRow, ConflictRow, DetectedEvent, ExistingEvent
from event_detector.naming import generate_title, slugify

logger = logging.getLogger(__name__)

# --- Tuning knobs (sensible defaults, adjust with real data) ---------------

# Minimum number of shared entity QIDs for two articles to be connected.
MIN_SHARED_ENTITIES = 2

# Minimum sum of IDF scores of shared entities.  This filters out pairs
# that only share very common entities (like "United States").
MIN_IDF_SUM = 2.0

# Minimum number of articles in a cluster to create an event.
MIN_CLUSTER_SIZE = 3

# Heat formula constants.
HEAT_LAMBDA = 0.01  # Decay rate — heat halves roughly every 69 hours (~3 days).

# Lifecycle heat thresholds.
HEAT_ACTIVE = 5.0  # emerging → active
HEAT_COOLING = 2.0  # active → cooling
HEAT_HISTORICAL = 0.5  # any → historical

# Jaccard similarity threshold for matching a cluster to an existing event.
JACCARD_THRESHOLD = 0.3



# --- IDF computation -------------------------------------------------------


def compute_entity_idf(articles: list[ArticleRow]) -> dict[str, float]:
    """Compute inverse document frequency for each entity QID.

    IDF = log(total_articles / articles_containing_entity)

    An entity in 1 of 100 articles → IDF ≈ 4.6 (very distinctive).
    An entity in 50 of 100 articles → IDF ≈ 0.7 (common, downweighted).
    """
    total = len(articles)
    if total == 0:
        return {}

    doc_counts: dict[str, int] = defaultdict(int)
    for article in articles:
        qids = _extract_qids(article)
        for qid in qids:
            doc_counts[qid] += 1

    return {qid: math.log(total / count) for qid, count in doc_counts.items()}


# --- Article clustering ----------------------------------------------------


def cluster_articles(
    articles: list[ArticleRow],
    idf: dict[str, float],
) -> list[list[ArticleRow]]:
    """Group articles into clusters by entity QID overlap.

    Two articles are connected if they share >= MIN_SHARED_ENTITIES QIDs
    and the sum of those QIDs' IDF scores >= MIN_IDF_SUM.  Clusters are
    the connected components of this graph.
    """
    # Build QID sets per article.
    article_qids: list[set[str]] = [_extract_qids(a) for a in articles]

    # Build adjacency list.  Only compare articles that share at least one QID
    # (via an inverted index) to avoid O(n^2) in the common case.
    qid_to_articles: dict[str, list[int]] = defaultdict(list)
    for idx, qids in enumerate(article_qids):
        for qid in qids:
            qid_to_articles[qid].append(idx)

    adj: dict[int, set[int]] = defaultdict(set)
    for indices in qid_to_articles.values():
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                a, b = indices[i], indices[j]
                if a in adj.get(b, set()):
                    continue  # Already connected.
                shared = article_qids[a] & article_qids[b]
                if len(shared) < MIN_SHARED_ENTITIES:
                    continue
                idf_sum = sum(idf.get(q, 0.0) for q in shared)
                if idf_sum < MIN_IDF_SUM:
                    continue
                adj[a].add(b)
                adj[b].add(a)

    # BFS to find connected components.
    visited: set[int] = set()
    components: list[list[int]] = []
    for idx in range(len(articles)):
        if idx in visited:
            continue
        # Only start a component if this article has at least one edge.
        if idx not in adj:
            continue
        component: list[int] = []
        queue = [idx]
        while queue:
            node = queue.pop()
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            for neighbor in adj.get(node, set()):
                if neighbor not in visited:
                    queue.append(neighbor)
        components.append(component)

    # Filter to clusters meeting minimum size.
    return [[articles[i] for i in comp] for comp in components if len(comp) >= MIN_CLUSTER_SIZE]


# --- Heat scoring -----------------------------------------------------------


def compute_heat(
    article_count: int,
    conflict_count: int,
    hours_since_last: float,
) -> float:
    """Score a cluster's current "heat".

    heat = article_count^0.5 * max(1, conflict_count^0.3) * exp(-λ * hours)

    Square root on article_count prevents large clusters from dominating
    smaller active ones (100 articles → 10x, not 100x, a single article).

    max(1, ...) on conflict_count ensures events with zero conflicts still
    have nonzero heat.
    """
    base = (article_count**0.5) * max(1.0, conflict_count**0.3)
    return base * math.exp(-HEAT_LAMBDA * max(0.0, hours_since_last))


def determine_status(heat: float, current_status: str | None = None) -> str:
    """Determine lifecycle status from heat value.

    Status transitions are non-linear — any state can jump to historical,
    and historical can re-emerge to active.
    """
    if heat < HEAT_HISTORICAL:
        return "historical"
    if heat >= HEAT_ACTIVE:
        return "active"
    if current_status == "active" and heat < HEAT_COOLING:
        return "cooling"
    if current_status == "cooling":
        return "cooling"
    return "emerging"


# --- Conflict matching ------------------------------------------------------


def extract_countries(cluster: list[ArticleRow]) -> set[str]:
    """Extract country names from GPE entities whose Wikidata description contains 'country'.

    This relies on the entity-resolver enriching each entity with its Wikidata
    description.  Country-level entities always have descriptions like
    "country in Western Asia" or "country in South America", so checking for
    the substring "country" in the description is a simple and reliable heuristic.
    """
    countries: set[str] = set()
    for article in cluster:
        for ent in article.entities:
            if ent.get("label") != "GPE":
                continue
            desc = (ent.get("description") or "").lower()
            if "country" not in desc:
                continue
            name = ent.get("canonical_name") or ent.get("text", "")
            if name:
                countries.add(name)
    return countries


def match_conflicts(
    cluster_countries: set[str],
    conflicts: list[ConflictRow],
) -> list[int]:
    """Find conflict events whose country overlaps with the cluster's countries.

    Uses case-insensitive matching since country names from different sources
    (Wikidata vs GDELT/UCDP) may differ in casing.
    """
    if not cluster_countries:
        return []

    normalized = {c.lower().strip() for c in cluster_countries}

    matched: list[int] = []
    for conflict in conflicts:
        if conflict.country and conflict.country.lower().strip() in normalized:
            matched.append(conflict.id)
    return matched


# --- Event matching ---------------------------------------------------------


def match_existing_event(
    cluster_qids: set[str],
    existing_events: list[ExistingEvent],
) -> ExistingEvent | None:
    """Find the existing event with the highest Jaccard overlap.

    Jaccard = |A ∩ B| / |A ∪ B|

    Returns the best match above JACCARD_THRESHOLD, or None.
    """
    best_event: ExistingEvent | None = None
    best_jaccard = 0.0

    for event in existing_events:
        event_qids = set(event.entity_qids)
        intersection = cluster_qids & event_qids
        union = cluster_qids | event_qids
        if not union:
            continue
        jaccard = len(intersection) / len(union)
        if jaccard >= JACCARD_THRESHOLD and jaccard > best_jaccard:
            best_jaccard = jaccard
            best_event = event

    return best_event


# --- Cluster → DetectedEvent ------------------------------------------------


def build_event(
    cluster: list[ArticleRow],
    conflicts: list[ConflictRow],
    idf: dict[str, float],
    existing: ExistingEvent | None,
) -> DetectedEvent:
    """Convert a cluster of articles into a DetectedEvent."""
    # Collect all QIDs in the cluster, counting occurrences.
    qid_counts: Counter[str] = Counter()
    entity_names: dict[str, str] = {}
    for article in cluster:
        for ent in article.entities:
            qid = ent.get("wikidata_id")
            if not qid:
                continue
            qid_counts[qid] += 1
            if qid not in entity_names:
                entity_names[qid] = ent.get("canonical_name") or ent.get("text", "")

    # Core entity QIDs: those appearing in at least 2 articles.
    core_qids = [qid for qid, count in qid_counts.most_common() if count >= 2]
    if not core_qids:
        # Fallback: take all QIDs sorted by count.
        core_qids = [qid for qid, _ in qid_counts.most_common()]

    # Compute centroid from entity coordinates (used for map display).
    centroid_lat, centroid_lng = _compute_centroid(cluster)

    # Match conflicts by country overlap.
    cluster_countries = extract_countries(cluster)
    matched_conflict_ids = match_conflicts(cluster_countries, conflicts)

    # Timing.
    now = datetime.now(timezone.utc)
    article_dates = [a.published_at for a in cluster if a.published_at]
    last_seen = max(article_dates) if article_dates else now
    first_seen = existing.first_seen if existing else (min(article_dates) if article_dates else now)

    hours_since_last = (now - last_seen).total_seconds() / 3600.0

    heat = compute_heat(len(cluster), len(matched_conflict_ids), hours_since_last)
    status = determine_status(heat, existing.status if existing else None)

    # Naming.
    article_labels = [a.automatic_labels for a in cluster]
    title = generate_title(core_qids, entity_names, idf, article_labels)
    slug = existing.slug if existing else slugify(title)

    return DetectedEvent(
        slug=slug,
        title=title,
        status=status,
        heat=round(heat, 4),
        entity_qids=core_qids,
        centroid_lat=centroid_lat,
        centroid_lng=centroid_lng,
        first_seen=first_seen,
        last_seen=last_seen,
        article_ids=[a.id for a in cluster],
        conflict_ids=matched_conflict_ids,
        existing_id=existing.id if existing else None,
    )


# --- Helpers ----------------------------------------------------------------


def _extract_qids(article: ArticleRow) -> set[str]:
    """Extract the set of Wikidata QIDs from an article's entities."""
    return {ent["wikidata_id"] for ent in article.entities if ent.get("wikidata_id")}


def _compute_centroid(cluster: list[ArticleRow]) -> tuple[float | None, float | None]:
    """Average lat/lng across all geo-located entities in the cluster."""
    lats: list[float] = []
    lngs: list[float] = []
    for article in cluster:
        for ent in article.entities:
            lat = ent.get("latitude")
            lng = ent.get("longitude")
            if lat is not None and lng is not None:
                lats.append(float(lat))
                lngs.append(float(lng))

    if not lats:
        return None, None
    return sum(lats) / len(lats), sum(lngs) / len(lngs)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points on Earth, in kilometres.

    Uses the Haversine formula.  Accurate enough for our ~100km threshold.
    """
    R = 6371.0  # Earth radius in km.
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
