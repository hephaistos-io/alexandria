from dataclasses import dataclass


@dataclass
class ResolvedArticle:
    """An article with entities enriched with Wikidata resolution."""

    source: str
    origin: str
    title: str
    url: str
    summary: str
    published: str | None
    fetched_at: str
    content: str
    scraped_at: str
    entities: list[dict]  # enriched with wikidata_id, canonical_name, description
    tagged_at: str
    resolved_at: str  # ISO 8601
