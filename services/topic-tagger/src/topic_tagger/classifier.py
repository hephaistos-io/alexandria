"""TopicClassifier — wraps a zero-shot classification pipeline from transformers.

Zero-shot classification means the model was never trained on our specific
labels. Instead, it uses natural language inference to decide whether a piece
of text entails a hypothesis like "This text is about CONFLICT".

Model: MoritzLaurer/deberta-v3-base-zeroshot-v2.0
  - Small enough to run on CPU in a container (~300MB)
  - Designed specifically for zero-shot classification
  - Outperforms facebook/bart-large-mnli on most benchmarks at 1/10 the size

multi_label=True means the model scores each candidate label independently
rather than forcing them to sum to 1. An article can legitimately cover
CONFLICT and POLITICS simultaneously.

threshold: scores below this are discarded. 0.3 is a conservative starting
point — high enough to suppress noise, low enough not to miss real topics.
Tune this based on observed precision/recall.
"""

import logging

from transformers import pipeline  # type: ignore[import-untyped]

from topic_tagger.labels import LabelDefinition

logger = logging.getLogger(__name__)

MODEL_NAME = "MoritzLaurer/deberta-v3-base-zeroshot-v2.0"
HYPOTHESIS_TEMPLATE = "This text is about {}"


class TopicClassifier:
    """Classifies article text against a set of candidate topic labels.

    The key insight: we feed the label *descriptions* (not names) to the
    zero-shot model as NLI hypotheses. "This text is about armed conflicts,
    wars, and military operations" gives the model far more signal than
    "This text is about CONFLICT". The name is just for storage/display.

    The pipeline is loaded once at construction (expensive) and reused
    for every classify() call. Calling update_labels() hot-reloads the
    label list without reloading the model — this lets us pick up new
    labels from the DB without restarting the service.
    """

    def __init__(
        self,
        labels: list[LabelDefinition],
        threshold: float = 0.3,
        max_labels: int = 3,
        model: str = MODEL_NAME,
    ) -> None:
        # device=-1 forces CPU inference. On CPU, deberta-v3-xsmall takes
        # ~0.5–1s per article, which is acceptable for a background pipeline.
        logger.info("Loading classification model '%s' on CPU", model)
        self._pipe = pipeline(
            "zero-shot-classification",
            model=model,
            device=-1,
        )
        self._labels = labels
        self._threshold = threshold
        self._max_labels = max_labels
        logger.info(
            "Classifier ready with %d labels, threshold=%.2f, max_labels=%d",
            len(labels),
            threshold,
            max_labels,
        )

    def update_labels(self, labels: list[LabelDefinition]) -> None:
        """Replace the candidate label list.

        Called periodically to pick up label changes from the DB without
        restarting the process.
        """
        self._labels = labels
        logger.info("Label list updated: %s", [label.name for label in labels])

    def classify(self, text: str) -> list[dict]:
        """Classify text against the current candidate labels.

        Returns a list of {"name": str, "score": float} dicts for labels
        that scored above the threshold. Empty list if none qualify.

        The descriptions are used as NLI hypotheses — the model sees e.g.
        "This text is about armed conflicts, wars, military operations"
        not "This text is about CONFLICT". After scoring, we map back to
        the label names for storage.
        """
        # Snapshot the label list so a concurrent update_labels() call from
        # the refresh timer can't swap descriptions between building desc_to_name
        # and using it to reverse-map the model's output.
        labels = self._labels
        if not labels:
            return []

        # Build a mapping from description → name so we can reverse-map
        # the model's output back to label names.
        desc_to_name = {label.description: label.name for label in labels}
        descriptions = list(desc_to_name.keys())

        result = self._pipe(
            text,
            candidate_labels=descriptions,
            hypothesis_template=HYPOTHESIS_TEMPLATE,
            multi_label=True,
        )

        # result["labels"] and result["scores"] are parallel lists, ordered
        # by descending score. The labels here are our descriptions — map
        # them back to the label names.
        hits = [
            {"name": desc_to_name[desc], "score": round(score, 4)}
            for desc, score in zip(result["labels"], result["scores"])
            if score >= self._threshold
        ]

        return hits[: self._max_labels]
