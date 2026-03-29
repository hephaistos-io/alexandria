"""RoleClassifier — classifies the role of geographic entities within articles.

Zero-shot classification means the model was never trained on our specific
role labels. Instead, it uses natural language inference to decide whether
a piece of text entails a hypothesis like "In this context, Iran is a source
of the conflict described".

Model: MoritzLaurer/deberta-v3-base-zeroshot-v2.0
  - Small enough to run on CPU in a container (~300MB)
  - Designed specifically for zero-shot classification
  - Outperforms facebook/bart-large-mnli on most benchmarks at 1/10 the size

multi_label=False for role classification because an entity plays one
dominant role in a given article. This makes the model's scores sum to 1
(softmax) and we simply take the top result.
"""

import logging

from transformers import pipeline  # type: ignore[import-untyped]

from role_classifier.labels import LabelDefinition

logger = logging.getLogger(__name__)

MODEL_NAME = "MoritzLaurer/deberta-v3-base-zeroshot-v2.0"

# Entity label types that represent geographic or place entities.
# These are the spaCy NER labels we expect to see on geo entities.
GEO_LABELS = {"GPE", "LOC", "FAC"}


def _extract_sentence(content: str, start: int, end: int) -> str:
    """Return the sentence containing the character range [start, end).

    We look backwards from `start` for a sentence-ending punctuation mark
    (period or newline) and forwards from `end` for the same. This is
    intentionally simple — we don't need perfect sentence segmentation here,
    just enough local context for the model to make a sensible role decision.

    If the content string is empty or the offsets are out of range, an empty
    string is returned and the caller falls back to using just the title.
    """
    if not content:
        return ""

    # Clamp offsets to valid range to guard against bad entity spans.
    start = max(0, min(start, len(content)))
    end = max(start, min(end, len(content)))

    # Walk backwards to find the start of the sentence.
    sent_start = start
    while sent_start > 0 and content[sent_start - 1] not in (".", "\n"):
        sent_start -= 1

    # Walk forwards to find the end of the sentence.
    sent_end = end
    while sent_end < len(content) and content[sent_end] not in (".", "\n"):
        sent_end += 1

    return content[sent_start:sent_end].strip()


class RoleClassifier:
    """Classifies the role of geographic entities within an article.

    The key insight: we build an entity-specific NLI hypothesis per entity:
      "In this context, {entity name} is {role description}"
    This forces the model to reason about this particular entity's role,
    not just the article's general topic.

    The pipeline is loaded once at construction (expensive) and reused for
    every classify_entity_roles() call. Calling update_role_types() hot-reloads
    the role type list without reloading the model — this lets us pick up new
    role types from the DB without restarting the service.
    """

    def __init__(
        self,
        role_types: list[LabelDefinition],
        model: str = MODEL_NAME,
    ) -> None:
        # device=-1 forces CPU inference. On CPU, deberta-v3-base takes
        # ~0.5–1s per entity, which is acceptable for a background pipeline.
        logger.info("Loading classification model '%s' on CPU", model)
        self._pipe = pipeline(
            "zero-shot-classification",
            model=model,
            device=-1,
        )
        self._role_types = role_types
        logger.info("RoleClassifier ready with %d role types", len(role_types))

    def update_role_types(self, role_types: list[LabelDefinition]) -> None:
        """Replace the candidate role type list.

        Called periodically to pick up role type changes from the DB without
        restarting the process.  Only logs when the list actually changes to
        avoid noisy repeated output every refresh cycle.
        """
        new_names = [r.name for r in role_types]
        old_names = [r.name for r in self._role_types]
        if new_names != old_names:
            logger.info("Role type list updated: %s", new_names)
        self._role_types = role_types

    def classify_entity_roles(
        self,
        entities: list[dict],
        title: str,
        content: str,
    ) -> list[dict]:
        """Classify the role of each geographic entity within the article.

        For each GPE/LOC/FAC entity we build a short, entity-specific input:
          "{title}. {sentence containing the entity}"
        then run zero-shot classification against the role type descriptions,
        using multi_label=False because an entity plays one dominant role.

        The winning role and its confidence score are written directly onto
        the entity dict as auto_role and auto_role_confidence. Entities of
        non-geographic types are left untouched.

        Returns the same list with the geo entities mutated in place. The
        return value is the list itself — we return it for convenience so
        callers can do: entities = classifier.classify_entity_roles(...).
        """
        if not self._role_types or not entities:
            return entities

        desc_to_name = {r.description: r.name for r in self._role_types}
        descriptions = list(desc_to_name.keys())

        for entity in entities:
            if entity.get("label") not in GEO_LABELS:
                continue

            # Prefer the resolved canonical name; fall back to the raw text span.
            name = entity.get("canonical_name") or entity.get("text", "")
            if not name:
                logger.debug("Skipping entity with no name: %s", entity)
                continue

            # Use the sentence containing the entity mention for local context.
            # Without this, the model only sees the title, which is often too
            # vague to distinguish ACTOR from TARGET.
            start = entity.get("start", 0)
            end = entity.get("end", 0)
            sentence = _extract_sentence(content, start, end)
            text_input = f"{title}. {sentence}" if sentence else title

            # The hypothesis is entity-specific: "In this context, Iran is a source..."
            # This forces the model to reason about this particular entity's role,
            # not just the article's general topic.
            hypothesis_template = f"In this context, {name} is " + "{}"

            result = self._pipe(
                text_input,
                candidate_labels=descriptions,
                hypothesis_template=hypothesis_template,
                multi_label=False,
            )

            # result["labels"][0] is the top-scoring description — map it back
            # to the role name and record the confidence.
            top_desc = result["labels"][0]
            top_score = result["scores"][0]
            entity["auto_role"] = desc_to_name[top_desc]
            entity["auto_role_confidence"] = round(top_score, 4)

            logger.debug(
                "Entity '%s' → role=%s (%.3f)",
                name,
                entity["auto_role"],
                top_score,
            )

        return entities
