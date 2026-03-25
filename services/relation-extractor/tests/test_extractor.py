"""Unit tests for RelationExtractor.

We mock the transformers pipeline so these tests run without downloading
any model weights — fast CI, no GPU required.
"""

from unittest.mock import MagicMock, patch

from relation_extractor.extractor import (
    RelationExtractor,
    _entity_sentence_indices,
    _pairs_are_adjacent,
    _split_sentences,
)
from relation_extractor.labels import RelationDefinition

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DIRECTED_REL = RelationDefinition(name="ATTACKS", description="attacks", directed=True)
UNDIRECTED_REL = RelationDefinition(
    name="ALLIED_WITH", description="is allied with", directed=False
)


def _make_entity(qid: str, name: str, start: int, end: int, label: str = "GPE") -> dict:
    return {
        "wikidata_id": qid,
        "canonical_name": name,
        "text": name,
        "label": label,
        "start": start,
        "end": end,
    }


def _make_extractor(
    relation_types: list[RelationDefinition],
    threshold: float = 0.5,
) -> RelationExtractor:
    """Build a RelationExtractor with the pipeline replaced by a MagicMock."""
    with patch("relation_extractor.extractor.pipeline") as mock_pipeline_ctor:
        mock_pipeline_ctor.return_value = MagicMock()
        extractor = RelationExtractor(
            relation_types=relation_types,
            threshold=threshold,
            model="mock-model",
        )
    return extractor


# ---------------------------------------------------------------------------
# _split_sentences
# ---------------------------------------------------------------------------

class TestSplitSentences:
    def test_empty_content_returns_empty(self) -> None:
        assert _split_sentences("") == []

    def test_single_sentence_with_period(self) -> None:
        result = _split_sentences("Hello world.")
        assert len(result) == 1
        text, start, end = result[0]
        assert text == "Hello world."

    def test_multiple_sentences(self) -> None:
        content = "First sentence. Second sentence. Third sentence."
        result = _split_sentences(content)
        assert len(result) == 3
        assert result[0][0] == "First sentence."
        assert result[1][0] == "Second sentence."
        assert result[2][0] == "Third sentence."

    def test_newline_as_boundary(self) -> None:
        content = "Line one.\nLine two."
        result = _split_sentences(content)
        assert len(result) == 2
        assert result[0][0] == "Line one."
        assert result[1][0] == "Line two."

    def test_trailing_text_without_terminator(self) -> None:
        content = "First sentence. Trailing without period"
        result = _split_sentences(content)
        assert len(result) == 2
        assert result[1][0] == "Trailing without period"

    def test_offsets_are_consistent(self) -> None:
        content = "First. Second."
        result = _split_sentences(content)
        # Each returned offset should index back into the original content.
        for text, start, end in result:
            assert content[start:end].strip() == text

    def test_whitespace_only_segments_are_skipped(self) -> None:
        # Multiple sentence terminators in a row shouldn't produce empty sentences.
        content = "First..Second."
        result = _split_sentences(content)
        # "First." and "." (empty after strip) and "Second."
        # Empty segments should not appear.
        for text, _s, _e in result:
            assert text.strip() != ""


# ---------------------------------------------------------------------------
# _entity_sentence_indices
# ---------------------------------------------------------------------------

class TestEntitySentenceIndices:
    def test_entity_in_first_sentence(self) -> None:
        # "Iran attacked Syria." — Iran is at [0, 4)
        sentences = [("Iran attacked Syria.", 0, 20), ("Later, peace was reached.", 21, 46)]
        entity = {"start": 0, "end": 4}
        indices = _entity_sentence_indices(entity, sentences)
        assert indices == [0]

    def test_entity_in_second_sentence(self) -> None:
        sentences = [("First sentence.", 0, 15), ("Entity is here.", 16, 31)]
        entity = {"start": 23, "end": 29}
        indices = _entity_sentence_indices(entity, sentences)
        assert indices == [1]

    def test_entity_spanning_boundary(self) -> None:
        # An entity whose span crosses a sentence boundary appears in both.
        sentences = [("Sentence one.", 0, 13), ("Two.", 14, 18)]
        entity = {"start": 10, "end": 15}
        indices = _entity_sentence_indices(entity, sentences)
        assert 0 in indices
        assert 1 in indices

    def test_entity_with_no_matching_sentence(self) -> None:
        sentences = [("Short.", 0, 6)]
        entity = {"start": 100, "end": 110}
        indices = _entity_sentence_indices(entity, sentences)
        assert indices == []


# ---------------------------------------------------------------------------
# _pairs_are_adjacent
# ---------------------------------------------------------------------------

class TestPairsAreAdjacent:
    def test_same_sentence(self) -> None:
        assert _pairs_are_adjacent([2], [2]) is True

    def test_adjacent_sentences(self) -> None:
        assert _pairs_are_adjacent([1], [2]) is True
        assert _pairs_are_adjacent([3], [2]) is True

    def test_non_adjacent_sentences(self) -> None:
        assert _pairs_are_adjacent([0], [2]) is False
        assert _pairs_are_adjacent([0], [5]) is False

    def test_one_entity_in_multiple_sentences(self) -> None:
        # Entity A is in sentences 0 and 1; entity B is in sentence 3.
        # Sentence 1 and 3 have gap 2 — not adjacent. But 0 and 1 vs 3: no adjacent pair.
        assert _pairs_are_adjacent([0, 1], [3]) is False

    def test_one_entity_adjacent_via_multi_sentence(self) -> None:
        # Entity A is in sentences 0 and 2; entity B is in sentence 1.
        # Sentence 2 and 1 are adjacent.
        assert _pairs_are_adjacent([0, 2], [1]) is True


# ---------------------------------------------------------------------------
# RelationExtractor.extract_relations — integration of the full pipeline
# ---------------------------------------------------------------------------

class TestExtractRelations:
    def test_empty_entities_returns_empty(self) -> None:
        extractor = _make_extractor([DIRECTED_REL])
        result = extractor.extract_relations([], "Title", "Some content.")
        assert result == []

    def test_no_relation_types_returns_empty(self) -> None:
        extractor = _make_extractor([])
        entities = [
            _make_entity("Q1", "Iran", 0, 4),
            _make_entity("Q2", "Syria", 5, 10),
        ]
        result = extractor.extract_relations(entities, "Title", "Iran and Syria conflict.")
        assert result == []

    def test_unresolved_entities_are_filtered(self) -> None:
        """Entities without wikidata_id must not participate in pair enumeration."""
        extractor = _make_extractor([DIRECTED_REL])
        # Only one entity has a QID — no pairs can be formed.
        entities = [
            _make_entity("Q1", "Iran", 0, 4),
            {"text": "Syria", "label": "GPE", "start": 5, "end": 10},  # no wikidata_id
        ]
        result = extractor.extract_relations(entities, "Title", "Iran and Syria.")
        assert result == []

    def test_single_resolved_entity_returns_empty(self) -> None:
        extractor = _make_extractor([DIRECTED_REL])
        entities = [_make_entity("Q1", "Iran", 0, 4)]
        result = extractor.extract_relations(entities, "Title", "Iran is involved.")
        assert result == []

    def test_directed_relation_above_threshold(self) -> None:
        """A directed relation above threshold should produce a A→B edge."""
        extractor = _make_extractor([DIRECTED_REL], threshold=0.5)

        content = "Iran attacks Syria."
        entities = [
            _make_entity("Q1", "Iran", 0, 4),
            _make_entity("Q2", "Syria", 12, 17),
        ]

        # Simulate pipeline returning high confidence for the "attacks" candidate.
        forward_label = "Iran attacks Syria"
        extractor._pipe.return_value = {
            "labels": [forward_label],
            "scores": [0.85],
        }

        result = extractor.extract_relations(entities, "Title", content)
        assert len(result) == 1
        rel = result[0]
        assert rel["source_qid"] == "Q1"
        assert rel["target_qid"] == "Q2"
        assert rel["relation_type"] == "ATTACKS"
        assert rel["confidence"] == 0.85

    def test_directed_relation_below_threshold_is_filtered(self) -> None:
        extractor = _make_extractor([DIRECTED_REL], threshold=0.7)

        content = "Iran and Syria met."
        entities = [
            _make_entity("Q1", "Iran", 0, 4),
            _make_entity("Q2", "Syria", 9, 14),
        ]

        forward_label = "Iran attacks Syria"
        extractor._pipe.return_value = {
            "labels": [forward_label],
            "scores": [0.4],
        }

        result = extractor.extract_relations(entities, "Title", content)
        assert result == []

    def test_undirected_relation_canonicalization_smaller_qid_is_source(self) -> None:
        """For undirected relations, the entity with the smaller QID must be source."""
        extractor = _make_extractor([UNDIRECTED_REL], threshold=0.5)

        content = "Syria and Iran are allied."
        entities = [
            # Q2 comes first in the text but Q1 < Q2, so Q1 should be source.
            _make_entity("Q2", "Syria", 0, 5),
            _make_entity("Q1", "Iran", 10, 14),
        ]

        # Pipeline will be called with Syria as entity_a (first in unique_entities
        # after de-dup, preserving order from resolved list).
        # The undirected logic takes max(forward, reverse) and canonicalizes.
        forward_label = "Syria is allied with Iran"
        reverse_label = "Iran is allied with Syria"
        extractor._pipe.return_value = {
            "labels": [forward_label, reverse_label],
            "scores": [0.6, 0.75],
        }

        result = extractor.extract_relations(entities, "Title", content)
        assert len(result) == 1
        rel = result[0]
        # Q1 < Q2, so Q1 (Iran) should be source regardless of text order.
        assert rel["source_qid"] == "Q1"
        assert rel["target_qid"] == "Q2"
        assert rel["relation_type"] == "ALLIED_WITH"
        # max(0.6, 0.75) = 0.75
        assert rel["confidence"] == 0.75

    def test_non_adjacent_entities_are_skipped(self) -> None:
        """Entities that appear far apart in the article should not be paired."""
        extractor = _make_extractor([DIRECTED_REL], threshold=0.5)

        # Build content where entity A is in sentence 0 and entity B is in sentence 2.
        # Sentence offsets: "Iran did something. Middle sentence. Syria did something."
        #                    0123456789...        20..             36..
        content = "Iran did something. Middle sentence. Syria did something."
        entities = [
            _make_entity("Q1", "Iran", 0, 4),    # sentence 0
            _make_entity("Q2", "Syria", 37, 42),  # sentence 2 — gap of 2, not adjacent
        ]

        result = extractor.extract_relations(entities, "Title", content)
        # Pipeline should not have been called since the pair was skipped.
        extractor._pipe.assert_not_called()
        assert result == []

    def test_multiple_relations_on_one_pair(self) -> None:
        """An entity pair can have multiple relation types simultaneously."""
        rel_a = RelationDefinition(name="ATTACKS", description="attacks", directed=True)
        rel_b = RelationDefinition(name="THREATENS", description="threatens", directed=True)

        extractor = _make_extractor([rel_a, rel_b], threshold=0.5)

        content = "Iran attacks and threatens Syria."
        entities = [
            _make_entity("Q1", "Iran", 0, 4),
            _make_entity("Q2", "Syria", 26, 31),
        ]

        extractor._pipe.return_value = {
            "labels": ["Iran attacks Syria", "Iran threatens Syria"],
            "scores": [0.9, 0.8],
        }

        result = extractor.extract_relations(entities, "Title", content)
        relation_types = {r["relation_type"] for r in result}
        assert relation_types == {"ATTACKS", "THREATENS"}

    def test_duplicate_qid_entities_deduplicated(self) -> None:
        """If the same QID appears twice (two mentions), it should be treated as one entity."""
        extractor = _make_extractor([DIRECTED_REL], threshold=0.5)

        content = "Iran and Iran both attacked Syria."
        entities = [
            _make_entity("Q1", "Iran", 0, 4),
            _make_entity("Q1", "Iran", 9, 13),  # same QID, second mention
            _make_entity("Q2", "Syria", 27, 32),
        ]

        extractor._pipe.return_value = {
            "labels": ["Iran attacks Syria"],
            "scores": [0.9],
        }

        result = extractor.extract_relations(entities, "Title", content)
        # Should only produce one Q1→Q2 edge, not two.
        assert len(result) == 1
        assert result[0]["source_qid"] == "Q1"
        assert result[0]["target_qid"] == "Q2"
