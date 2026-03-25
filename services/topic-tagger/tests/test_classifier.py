"""Tests for TopicClassifier — topic classification via zero-shot NLI.

We mock the transformers pipeline to avoid requiring model weights at test time.

Entity role classification tests have moved to the role-classifier service.
"""

from unittest.mock import MagicMock, patch

import pytest

from topic_tagger.classifier import TopicClassifier
from topic_tagger.labels import LabelDefinition


def _make_classifier(labels: list[LabelDefinition] | None = None) -> TopicClassifier:
    """Build a TopicClassifier with the transformers pipeline mocked out."""
    with patch("topic_tagger.classifier.pipeline") as mock_pipeline_factory:
        mock_pipeline_factory.return_value = MagicMock()
        classifier = TopicClassifier(
            labels=labels or [],
        )
    return classifier


class TestClassifyNoOp:
    def test_returns_empty_list_when_no_labels(self) -> None:
        classifier = _make_classifier(labels=[])
        result = classifier.classify("Some article about conflict")
        assert result == []


class TestClassifyHappyPath:
    def test_returns_matching_labels_above_threshold(self) -> None:
        labels = [
            LabelDefinition(name="CONFLICT", description="armed conflicts and wars"),
            LabelDefinition(name="POLITICS", description="political events and governance"),
        ]
        with patch("topic_tagger.classifier.pipeline") as mock_factory:
            mock_pipe = MagicMock(return_value={
                "labels": ["armed conflicts and wars", "political events and governance"],
                "scores": [0.85, 0.45],
            })
            mock_factory.return_value = mock_pipe
            classifier = TopicClassifier(labels=labels, threshold=0.3)

        result = classifier.classify("War erupted in the region")
        assert len(result) == 2
        assert result[0]["name"] == "CONFLICT"
        assert result[0]["score"] == pytest.approx(0.85, abs=0.001)
        assert result[1]["name"] == "POLITICS"

    def test_filters_below_threshold(self) -> None:
        labels = [
            LabelDefinition(name="CONFLICT", description="armed conflicts"),
            LabelDefinition(name="ECONOMY", description="economic events"),
        ]
        with patch("topic_tagger.classifier.pipeline") as mock_factory:
            mock_pipe = MagicMock(return_value={
                "labels": ["armed conflicts", "economic events"],
                "scores": [0.85, 0.15],
            })
            mock_factory.return_value = mock_pipe
            classifier = TopicClassifier(labels=labels, threshold=0.3)

        result = classifier.classify("War erupted")
        assert len(result) == 1
        assert result[0]["name"] == "CONFLICT"

    def test_respects_max_labels(self) -> None:
        labels = [
            LabelDefinition(name="A", description="a"),
            LabelDefinition(name="B", description="b"),
            LabelDefinition(name="C", description="c"),
        ]
        with patch("topic_tagger.classifier.pipeline") as mock_factory:
            mock_pipe = MagicMock(return_value={
                "labels": ["a", "b", "c"],
                "scores": [0.9, 0.8, 0.7],
            })
            mock_factory.return_value = mock_pipe
            classifier = TopicClassifier(labels=labels, threshold=0.3, max_labels=2)

        result = classifier.classify("Some text")
        assert len(result) == 2
