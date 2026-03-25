from dataclasses import dataclass


@dataclass
class RssArticle:
    """An article as received from the article-fetcher via the articles.rss queue.

    This is the input to the scraper — metadata only, no full text.
    Datetimes are kept as ISO 8601 strings (passthrough from the fetcher).
    """

    source: str
    origin: str
    title: str
    url: str
    summary: str
    published: str | None  # ISO 8601 or null
    fetched_at: str  # ISO 8601


@dataclass
class ScrapedArticle:
    """An article enriched with full text, published to the articles.raw queue.

    All original fields from RssArticle are preserved. The content field
    is the full article text extracted by trafilatura.
    """

    source: str
    origin: str
    title: str
    url: str
    summary: str
    published: str | None
    fetched_at: str
    content: str  # full article text from trafilatura
    scraped_at: str  # ISO 8601 — when we scraped it
