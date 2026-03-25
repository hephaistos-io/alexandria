from dataclasses import dataclass


@dataclass
class TaggedMention:
    """An entity mention found in text by spaCy NER.

    Carries the mention text, its NER label (GPE, ORG, PERSON, etc.),
    and character offsets into the source text.
    """

    text: str  # mention as it appears in the source, e.g. "Tehran"
    label: str  # spaCy NER label, e.g. "GPE"
    start_char: int  # character offset start (inclusive)
    end_char: int  # character offset end (exclusive)


@dataclass
class TaggedArticle:
    """An article enriched with NER entities, published to articles.tagged.

    All original fields from the scraped article are preserved. The entities
    field is a list of dicts (not TaggedMention) because plain dicts serialize
    cleanly with dataclasses.asdict() and match what JSON deserialization produces.
    """

    source: str
    origin: str
    title: str
    url: str
    summary: str
    published: str | None
    fetched_at: str
    content: str
    scraped_at: str
    entities: list[dict]  # [{"text", "label", "start", "end"}, ...]
    tagged_at: str  # ISO 8601 — when NER tagging was performed
