"""Fetch article URLs and extract full text using trafilatura."""

import logging
from datetime import datetime, timezone

from trafilatura import extract, fetch_url

from article_scraper.models import RssArticle, ScrapedArticle

logger = logging.getLogger(__name__)


def scrape_article(article: RssArticle) -> ScrapedArticle | None:
    """Fetch the article URL and extract full text.

    Returns a ScrapedArticle with the content field populated, or None
    if the fetch or extraction failed.

    trafilatura.fetch_url() handles HTTP requests internally — it returns
    None on network errors, timeouts, and non-200 responses.

    trafilatura.extract() takes an HTML string and returns the main text
    content, or None if it can't identify article content (e.g. login
    walls, image galleries, empty pages).
    """
    logger.info("Scraping %s", article.url)

    html = fetch_url(article.url)
    if html is None:
        logger.warning("Fetch failed (404/timeout/network error): %s", article.url)
        return None

    # Use trafilatura's balanced defaults — neither favor_recall nor
    # favor_precision. This gives a good trade-off between catching all
    # article paragraphs and filtering out sidebar/footer boilerplate.
    content = extract(html)
    if not content:
        logger.warning("Extraction returned empty content: %s", article.url)
        return None

    return ScrapedArticle(
        source=article.source,
        origin=article.origin,
        title=article.title,
        url=article.url,
        summary=article.summary,
        published=article.published,
        fetched_at=article.fetched_at,
        content=content,
        scraped_at=datetime.now(timezone.utc).isoformat(),
    )
