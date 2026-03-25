import spacy

from ner_tagger.models import TaggedMention


class NerTagger:
    """Extracts named entity mentions from text using spaCy.

    Loads a spaCy model on init and exposes a tag() method that takes
    raw text and returns tagged mentions. Does not resolve entities —
    that's the entity-resolver's job.

    The model is loaded once and reused across calls. In a worker pool,
    each worker loads its own model instance (~100MB for en_core_web_sm).
    """

    def __init__(self, model: str = "en_core_web_sm") -> None:
        self._nlp = spacy.load(model)

    def tag(self, text: str) -> list[TaggedMention]:
        """Extract named entity mentions from text.

        Returns a list of TaggedMention with the mention text, NER label,
        and character offsets. Order matches appearance in the text.
        """
        doc = self._nlp(text)
        return [
            TaggedMention(
                text=ent.text,
                label=ent.label_,
                start_char=ent.start_char,
                end_char=ent.end_char,
            )
            for ent in doc.ents
        ]
