"""RelationExtractor — extracts entity-pair relations using zero-shot NLI.

For each pair of resolved entities that co-occur in the same or adjacent
sentences, we test NLI hypotheses of the form:
    "In this context, {entity_A} {relation_description} {entity_B}"

Uses multi_label=True because an entity pair can have multiple relation
types simultaneously (e.g. two countries can both trade with AND be in
conflict at the same time).

Model: MoritzLaurer/deberta-v3-base-zeroshot-v2.0
  - Small enough to run on CPU in a container (~300MB)
  - Designed specifically for zero-shot classification
  - Outperforms facebook/bart-large-mnli on most benchmarks at 1/10 the size
"""

import logging
from itertools import combinations

from transformers import pipeline  # type: ignore[import-untyped]

from relation_extractor.labels import RelationDefinition

logger = logging.getLogger(__name__)

MODEL_NAME = "MoritzLaurer/deberta-v3-base-zeroshot-v2.0"

# Generic template — the candidate labels themselves already embed both
# entity names, so "{}" becomes the full "A description B" string.
_HYPOTHESIS_TEMPLATE = "In this context, {}"


def _split_sentences(content: str) -> list[tuple[str, int, int]]:
    """Split content into sentences, returning (text, start_offset, end_offset) tuples.

    Uses the same simple boundary detection as role-classifier's _extract_sentence:
    walks through content looking for '.' and '\\n' as sentence terminators.
    This intentionally avoids pulling in a full NLP sentence splitter — we just
    need good enough segmentation to find co-occurring entity pairs.

    Returns an empty list for empty content.
    """
    if not content:
        return []

    sentences = []
    sent_start = 0

    for i, ch in enumerate(content):
        if ch in (".", "\n"):
            # Include the terminator in the sentence, then strip surrounding whitespace.
            raw = content[sent_start : i + 1].strip()
            if raw:
                # Record the actual stripped boundaries for matching entity spans.
                # We compute the stripped start by finding the first non-whitespace
                # character after sent_start.
                stripped_start = sent_start
                while stripped_start <= i and content[stripped_start] in (" ", "\t", "\r", "\n"):
                    stripped_start += 1
                stripped_end = i + 1
                sentences.append((raw, stripped_start, stripped_end))
            sent_start = i + 1

    # Capture any trailing text that doesn't end with a sentence terminator.
    trailing = content[sent_start:].strip()
    if trailing:
        stripped_start = sent_start
        while stripped_start < len(content) and content[stripped_start] in (" ", "\t", "\r", "\n"):
            stripped_start += 1
        sentences.append((trailing, stripped_start, len(content)))

    return sentences


def _entity_sentence_indices(
    entity: dict,
    sentences: list[tuple[str, int, int]],
) -> list[int]:
    """Return the indices of sentences that overlap with the entity's character span.

    An entity may span across a sentence boundary (rare but possible), so we
    return all sentence indices whose [sent_start, sent_end) range overlaps
    the entity's [start, end) range.
    """
    start = entity.get("start", 0)
    end = entity.get("end", start)

    indices = []
    for idx, (_text, sent_start, sent_end) in enumerate(sentences):
        # Overlap check: entity starts before sentence ends AND entity ends after sentence starts.
        if start < sent_end and end > sent_start:
            indices.append(idx)
    return indices


def _pairs_are_adjacent(indices_a: list[int], indices_b: list[int]) -> bool:
    """Return True if the two entities co-occur in the same or adjacent sentences.

    We allow a gap of 1 between sentence indices (adjacent sentences) because
    entity mentions at sentence boundaries often have their relational context
    split across two sentences.
    """
    for i in indices_a:
        for j in indices_b:
            if abs(i - j) <= 1:
                return True
    return False


def _shared_sentence_text(
    indices_a: list[int],
    indices_b: list[int],
    sentences: list[tuple[str, int, int]],
) -> str:
    """Return the text of the sentence(s) shared by or adjacent to both entities.

    If the entities share a sentence, return that sentence's text.
    If they're in adjacent sentences, return both concatenated — this gives
    the model the full relational context across the boundary.
    """
    for i in indices_a:
        for j in indices_b:
            if i == j:
                return sentences[i][0]

    # No shared sentence — find the closest adjacent pair and return both.
    best_pair = None
    best_gap = float("inf")
    for i in indices_a:
        for j in indices_b:
            gap = abs(i - j)
            if gap < best_gap:
                best_gap = gap
                best_pair = (min(i, j), max(i, j))

    if best_pair is None:
        return ""

    lo, hi = best_pair
    return sentences[lo][0] + " " + sentences[hi][0]


class RelationExtractor:
    """Extracts typed relations between resolved entity pairs using zero-shot NLI.

    Strategy per article:
      1. Filter entities to those with a wikidata_id (resolved entities only).
      2. Split article content into sentences.
      3. Map each entity to the sentence indices it appears in.
      4. Enumerate unique entity pairs (by QID) that co-occur in the same or
         adjacent sentences — this limits NLI calls to contextually relevant pairs.
      5. For each pair, batch all relation type candidates into one NLI call.
      6. Post-process scores: directed types produce one candidate per relation,
         undirected types produce two (both orderings) and we take the max.
      7. Emit relations above the confidence threshold.

    The pipeline is loaded once at construction and reused across all articles.
    update_relation_types() hot-reloads the relation list without reloading
    the model.
    """

    def __init__(
        self,
        relation_types: list[RelationDefinition],
        threshold: float = 0.65,
        model: str = MODEL_NAME,
    ) -> None:
        # device=-1 forces CPU inference. deberta-v3-base takes ~0.5–2s per
        # entity pair on CPU, which is acceptable for a background pipeline.
        logger.info("Loading relation extraction model '%s' on CPU", model)
        self._pipe = pipeline(
            "zero-shot-classification",
            model=model,
            device=-1,
        )
        self._relation_types = relation_types
        self._threshold = threshold
        logger.info(
            "RelationExtractor ready with %d relation types, threshold=%.2f",
            len(relation_types),
            threshold,
        )

    def update_relation_types(self, relation_types: list[RelationDefinition]) -> None:
        """Replace the candidate relation type list.

        Called periodically to pick up relation type changes from the DB without
        restarting the process.
        """
        self._relation_types = relation_types
        logger.info("Relation type list updated: %s", [r.name for r in relation_types])

    def extract_relations(
        self,
        entities: list[dict],
        title: str,
        content: str,
    ) -> list[dict]:
        """Extract relations between entity pairs that co-occur near each other.

        Returns a list of relation dicts, each with:
            source_qid, source_name, source_type,
            target_qid, target_name, target_type,
            relation_type, confidence

        Only entities with a wikidata_id are considered — unresolved mentions
        can't be reliably de-duplicated and would generate noisy edges.
        """
        if not self._relation_types or not entities:
            return []

        # Only process entities that have been resolved to a Wikidata QID.
        resolved = [e for e in entities if e.get("wikidata_id")]
        if len(resolved) < 2:
            return []

        sentences = _split_sentences(content)
        if not sentences:
            # Fall back: treat the whole title as a single sentence so we can
            # still run NLI for articles with no parseable content.
            sentences = [(title, 0, len(title))]

        # Map each resolved entity to the sentence indices it appears in.
        entity_sentence_map: dict[str, list[int]] = {}
        for entity in resolved:
            qid = entity["wikidata_id"]
            indices = _entity_sentence_indices(entity, sentences)
            # Union across multiple mentions of the same entity in this article.
            if qid not in entity_sentence_map:
                entity_sentence_map[qid] = []
            for idx in indices:
                if idx not in entity_sentence_map[qid]:
                    entity_sentence_map[qid].append(idx)

        # De-duplicate entities by QID, keeping the first occurrence's metadata.
        seen_qids: set[str] = set()
        unique_entities: list[dict] = []
        for entity in resolved:
            qid = entity["wikidata_id"]
            if qid not in seen_qids:
                seen_qids.add(qid)
                unique_entities.append(entity)

        relations: list[dict] = []

        # Enumerate all unique unordered pairs.
        for entity_a, entity_b in combinations(unique_entities, 2):
            qid_a = entity_a["wikidata_id"]
            qid_b = entity_b["wikidata_id"]

            indices_a = entity_sentence_map.get(qid_a, [])
            indices_b = entity_sentence_map.get(qid_b, [])

            # Skip pairs that are too far apart — their relation is likely
            # independent of the shared context we'd build from adjacent sentences.
            if not _pairs_are_adjacent(indices_a, indices_b):
                continue

            shared_text = _shared_sentence_text(indices_a, indices_b, sentences)
            premise = f"{title}. {shared_text}" if shared_text else title

            name_a = entity_a.get("canonical_name") or entity_a.get("text", "")
            name_b = entity_b.get("canonical_name") or entity_b.get("text", "")

            # Build candidate labels for one batched NLI call.
            # Each entry is a full hypothesis string so we can use the generic
            # template "In this context, {}" — the pipeline fills in {} with
            # each candidate label verbatim.
            #
            # For directed relations: one candidate → "A desc B"
            # For undirected relations: two candidates → "A desc B" and "B desc A"
            # We track which candidate maps to which (relation_name, direction).
            candidates: list[str] = []
            # Each metadata entry: (relation_name, directed, is_forward)
            # is_forward=True means candidate represents A→B
            # is_forward=False means candidate represents B→A (undirected reverse)
            candidate_meta: list[tuple[str, bool, bool]] = []

            for rel in self._relation_types:
                forward_label = f"{name_a} {rel.description} {name_b}"
                candidates.append(forward_label)
                candidate_meta.append((rel.name, rel.directed, True))

                if not rel.directed:
                    # Test the reverse direction too — we'll take the max of
                    # both scores to decide if this undirected relation exists.
                    reverse_label = f"{name_b} {rel.description} {name_a}"
                    candidates.append(reverse_label)
                    candidate_meta.append((rel.name, rel.directed, False))

            if not candidates:
                continue

            result = self._pipe(
                premise,
                candidate_labels=candidates,
                hypothesis_template=_HYPOTHESIS_TEMPLATE,
                multi_label=True,
            )

            # Map label → score from the pipeline result.
            score_map: dict[str, float] = dict(zip(result["labels"], result["scores"]))

            # Aggregate scores per relation type.
            # For directed: score is the single forward candidate's score.
            # For undirected: score is max(forward, reverse); edge is canonicalized
            # so the entity with the lexicographically smaller QID is always source.
            rel_scores: dict[str, float] = {}
            for (rel_name, directed, is_forward), label in zip(candidate_meta, candidates):
                score = score_map.get(label, 0.0)
                if directed:
                    # Directed: only the forward candidate matters.
                    rel_scores[rel_name] = score
                else:
                    # Undirected: take the maximum across both orderings.
                    rel_scores[rel_name] = max(rel_scores.get(rel_name, 0.0), score)

            for rel in self._relation_types:
                score = rel_scores.get(rel.name, 0.0)
                if score < self._threshold:
                    continue

                if rel.directed:
                    # Directed edge: A is always source, B is always target.
                    source, target = entity_a, entity_b
                else:
                    # Undirected edge: canonicalize so smaller QID is source.
                    # This prevents storing the same relationship as both A→B and B→A.
                    if qid_a <= qid_b:
                        source, target = entity_a, entity_b
                    else:
                        source, target = entity_b, entity_a

                relations.append({
                    "source_qid": source["wikidata_id"],
                    "source_name": source.get("canonical_name") or source.get("text", ""),
                    "source_type": source.get("label", ""),
                    "target_qid": target["wikidata_id"],
                    "target_name": target.get("canonical_name") or target.get("text", ""),
                    "target_type": target.get("label", ""),
                    "relation_type": rel.name,
                    "confidence": round(score, 4),
                })

                logger.debug(
                    "Relation: %s -[%s]-> %s (%.3f)",
                    source.get("canonical_name"),
                    rel.name,
                    target.get("canonical_name"),
                    score,
                )

        return relations
