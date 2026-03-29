"""Tests for RoleClassifier — entity role classification and sentence extraction.

We mock the transformers pipeline to avoid requiring model weights at test time.
This lets the tests run fast and in CI without GPU or internet access.

The unit under test is the logic that selects which entities to classify,
builds the hypothesis template, extracts sentence context, and annotates the
entity dict. We verify that the model is called with the right arguments and
that the result is written to the right fields.
"""

from unittest.mock import MagicMock, patch

import pytest

from role_classifier.classifier import RoleClassifier, _extract_sentence
from role_classifier.labels import LabelDefinition

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_classifier(role_types: list[LabelDefinition] | None = None) -> RoleClassifier:
    """Build a RoleClassifier with the transformers pipeline mocked out.

    We patch `role_classifier.classifier.pipeline` so the model is never
    actually loaded — the test controls what the mock returns.
    """
    with patch("role_classifier.classifier.pipeline") as mock_pipeline_factory:
        mock_pipeline_factory.return_value = MagicMock()
        classifier = RoleClassifier(role_types=role_types or [])
    return classifier


def _make_classifier_with_mock_pipe(
    pipe_return_value: dict,
    role_types: list[LabelDefinition],
) -> tuple[RoleClassifier, MagicMock]:
    """Build a classifier whose pipeline is a controllable mock.

    Returns the classifier and the mock pipe object so tests can inspect
    how it was called.
    """
    with patch("role_classifier.classifier.pipeline") as mock_factory:
        mock_pipe = MagicMock(return_value=pipe_return_value)
        mock_factory.return_value = mock_pipe
        classifier = RoleClassifier(role_types=role_types)
    return classifier, mock_pipe


def _mock_pipe_result(label: str, score: float) -> dict:
    """Build the dict structure that the transformers zero-shot pipeline returns."""
    return {
        "labels": [label],
        "scores": [score],
    }


# ---------------------------------------------------------------------------
# _extract_sentence
# ---------------------------------------------------------------------------

class TestExtractSentence:
    def test_returns_sentence_containing_span(self) -> None:
        content = "The US imposed sanctions. Iran responded angrily. Talks broke down."
        start = content.index("Iran")
        end = start + len("Iran")
        sentence = _extract_sentence(content, start, end)
        assert "Iran" in sentence
        assert "responded" in sentence

    def test_first_sentence_no_preceding_period(self) -> None:
        content = "Iran is the key player here. Other nations disagreed."
        start = 0
        end = 4  # "Iran"
        sentence = _extract_sentence(content, start, end)
        assert sentence.startswith("Iran")

    def test_last_sentence_no_trailing_period(self) -> None:
        content = "Talks collapsed. Iran walked out"
        start = content.index("Iran")
        end = start + len("Iran")
        sentence = _extract_sentence(content, start, end)
        assert "Iran walked out" in sentence

    def test_empty_content_returns_empty_string(self) -> None:
        assert _extract_sentence("", 0, 5) == ""

    def test_newline_treated_as_sentence_boundary(self) -> None:
        content = "First paragraph.\nIran is here.\nThird paragraph."
        start = content.index("Iran")
        end = start + len("Iran")
        sentence = _extract_sentence(content, start, end)
        assert "Iran is here" in sentence
        assert "First paragraph" not in sentence
        assert "Third paragraph" not in sentence

    def test_out_of_range_start_clamped(self) -> None:
        content = "Short text."
        sentence = _extract_sentence(content, -10, 5)
        assert isinstance(sentence, str)

    def test_out_of_range_end_clamped(self) -> None:
        content = "Short text."
        sentence = _extract_sentence(content, 0, 999)
        assert isinstance(sentence, str)


# ---------------------------------------------------------------------------
# classify_entity_roles — no-op guards
# ---------------------------------------------------------------------------

class TestClassifyEntityRolesNoOp:
    def test_returns_entities_unchanged_when_no_role_types(self) -> None:
        classifier = _make_classifier(role_types=[])
        entities = [{"text": "Iran", "label": "GPE", "start": 0, "end": 4}]
        result = classifier.classify_entity_roles(entities, "Iran sanctions", "Iran was affected.")
        assert result == entities
        assert "auto_role" not in result[0]

    def test_returns_empty_list_when_no_entities(self) -> None:
        role_types = [LabelDefinition(name="ACTOR", description="the entity performing the primary action")]
        classifier = _make_classifier(role_types=role_types)
        result = classifier.classify_entity_roles([], "Title", "Content")
        assert result == []

    def test_skips_non_geo_entities(self) -> None:
        role_types = [LabelDefinition(name="ACTOR", description="the entity performing the primary action")]
        classifier = _make_classifier(role_types=role_types)
        entities = [
            {"text": "John Smith", "label": "PERSON", "start": 0, "end": 10},
            {"text": "Acme Corp", "label": "ORG", "start": 12, "end": 21},
        ]
        result = classifier.classify_entity_roles(entities, "Title", "Content")
        for entity in result:
            assert "auto_role" not in entity


# ---------------------------------------------------------------------------
# classify_entity_roles — happy path
# ---------------------------------------------------------------------------

class TestClassifyEntityRolesAnnotation:
    def test_annotates_gpe_entity(self) -> None:
        role_types = [
            LabelDefinition(name="ACTOR", description="the entity performing or initiating the primary action described"),
            LabelDefinition(name="TARGET", description="the entity being acted upon, impacted, or targeted"),
        ]
        pipe_result = _mock_pipe_result("the entity performing or initiating the primary action described", 0.82)
        classifier, _ = _make_classifier_with_mock_pipe(pipe_result, role_types)

        entities = [{"text": "Iran", "label": "GPE", "start": 0, "end": 4}]
        result = classifier.classify_entity_roles(
            entities, "Iran imposes sanctions", "Iran moved its forces."
        )
        assert result[0]["auto_role"] == "ACTOR"
        assert result[0]["auto_role_confidence"] == pytest.approx(0.82, abs=0.001)

    def test_annotates_loc_entity(self) -> None:
        role_types = [
            LabelDefinition(name="THEATER", description="the geographic theater of operations")
        ]
        pipe_result = _mock_pipe_result("the geographic theater of operations", 0.71)
        classifier, _ = _make_classifier_with_mock_pipe(pipe_result, role_types)

        entities = [{"text": "Strait of Hormuz", "label": "LOC", "start": 5, "end": 20}]
        result = classifier.classify_entity_roles(
            entities, "Tensions", "Ships near Strait of Hormuz blockaded."
        )
        assert result[0]["auto_role"] == "THEATER"

    def test_annotates_fac_entity(self) -> None:
        role_types = [
            LabelDefinition(name="TARGET", description="a target of the attack described")
        ]
        pipe_result = _mock_pipe_result("a target of the attack described", 0.90)
        classifier, _ = _make_classifier_with_mock_pipe(pipe_result, role_types)

        entities = [{"text": "Natanz", "label": "FAC", "start": 0, "end": 6}]
        result = classifier.classify_entity_roles(
            entities, "Attack on facility", "Natanz was struck overnight."
        )
        assert result[0]["auto_role"] == "TARGET"

    def test_uses_canonical_name_in_hypothesis(self) -> None:
        role_types = [
            LabelDefinition(name="ACTOR", description="the entity performing or initiating the primary action described")
        ]
        pipe_result = _mock_pipe_result("the entity performing or initiating the primary action described", 0.75)
        classifier, mock_pipe = _make_classifier_with_mock_pipe(pipe_result, role_types)

        entities = [{
            "text": "Tehran",
            "label": "GPE",
            "canonical_name": "Iran",
            "start": 0,
            "end": 6,
        }]
        classifier.classify_entity_roles(entities, "Tehran threatens", "Tehran issued a warning.")

        call_kwargs = mock_pipe.call_args
        hypothesis_used = call_kwargs[1]["hypothesis_template"]
        assert "Iran" in hypothesis_used
        assert "Tehran" not in hypothesis_used

    def test_falls_back_to_text_when_no_canonical_name(self) -> None:
        role_types = [
            LabelDefinition(name="TARGET", description="the entity being acted upon, impacted, or targeted")
        ]
        pipe_result = _mock_pipe_result("the entity being acted upon, impacted, or targeted", 0.68)
        classifier, mock_pipe = _make_classifier_with_mock_pipe(pipe_result, role_types)

        entities = [{"text": "Gaza", "label": "GPE", "start": 0, "end": 4}]
        classifier.classify_entity_roles(entities, "Conflict in Gaza", "Gaza suffered damage.")

        call_kwargs = mock_pipe.call_args
        hypothesis_used = call_kwargs[1]["hypothesis_template"]
        assert "Gaza" in hypothesis_used

    def test_uses_multi_label_false(self) -> None:
        """Entity role is a single-label task — the model should not score labels independently."""
        role_types = [
            LabelDefinition(name="ACTOR", description="performing the primary action"),
            LabelDefinition(name="TARGET", description="being acted upon or targeted"),
        ]
        pipe_result = _mock_pipe_result("performing the primary action", 0.9)
        classifier, mock_pipe = _make_classifier_with_mock_pipe(pipe_result, role_types)

        entities = [{"text": "Iran", "label": "GPE", "start": 0, "end": 4}]
        classifier.classify_entity_roles(entities, "Title", "Content")

        call_kwargs = mock_pipe.call_args
        assert call_kwargs[1]["multi_label"] is False

    def test_score_is_rounded_to_four_decimal_places(self) -> None:
        role_types = [LabelDefinition(name="ACTOR", description="performing the primary action")]
        pipe_result = _mock_pipe_result("performing the primary action", 0.8123456789)
        classifier, _ = _make_classifier_with_mock_pipe(pipe_result, role_types)

        entities = [{"text": "Iran", "label": "GPE", "start": 0, "end": 4}]
        result = classifier.classify_entity_roles(entities, "Title", "Content")
        assert result[0]["auto_role_confidence"] == 0.8123

    def test_only_geo_entities_annotated_mixed_list(self) -> None:
        role_types = [LabelDefinition(name="ACTOR", description="performing the primary action")]
        pipe_result = _mock_pipe_result("performing the primary action", 0.9)
        classifier, mock_pipe = _make_classifier_with_mock_pipe(pipe_result, role_types)

        entities = [
            {"text": "John Smith", "label": "PERSON", "start": 0, "end": 10},
            {"text": "Iran", "label": "GPE", "start": 12, "end": 16},
            {"text": "UN", "label": "ORG", "start": 18, "end": 20},
        ]
        result = classifier.classify_entity_roles(entities, "Title", "Content")

        assert "auto_role" not in result[0]  # PERSON skipped
        assert result[1]["auto_role"] == "ACTOR"  # GPE annotated
        assert "auto_role" not in result[2]  # ORG skipped
        assert mock_pipe.call_count == 1

    def test_entity_with_no_name_is_skipped(self) -> None:
        """An entity dict missing both text and canonical_name must not crash."""
        role_types = [LabelDefinition(name="ACTOR", description="performing the primary action")]
        pipe_result = _mock_pipe_result("performing the primary action", 0.9)
        classifier, mock_pipe = _make_classifier_with_mock_pipe(pipe_result, role_types)

        entities = [{"label": "GPE", "start": 0, "end": 4}]
        result = classifier.classify_entity_roles(entities, "Title", "Content")

        assert mock_pipe.call_count == 0
        assert "auto_role" not in result[0]

    def test_title_used_alone_when_content_empty(self) -> None:
        """When content is empty the input falls back to just the title."""
        role_types = [LabelDefinition(name="ACTOR", description="performing the primary action")]
        pipe_result = _mock_pipe_result("performing the primary action", 0.75)
        classifier, mock_pipe = _make_classifier_with_mock_pipe(pipe_result, role_types)

        entities = [{"text": "Iran", "label": "GPE", "start": 0, "end": 4}]
        classifier.classify_entity_roles(entities, "Iran news", "")

        text_used = mock_pipe.call_args[0][0]
        assert text_used == "Iran news"
