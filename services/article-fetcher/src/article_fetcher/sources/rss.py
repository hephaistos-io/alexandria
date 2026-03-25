import html
import logging
from calendar import timegm
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser

from article_fetcher.base import DataFetcher
from article_fetcher.models import Article

logger = logging.getLogger(__name__)


class RssFetcher(DataFetcher):
    """Fetches articles from any RSS feed.

    Parses standard RSS 2.0 feeds via feedparser. Source-agnostic — just
    point it at a feed URL. Defaults to BBC World News (free, no auth).

    Some feeds append tracking parameters to article URLs (e.g. Al Jazeera's
    ``?traffic_source=rss``, DW's ``?maca=...``). Pass a ``url_cleaner``
    callable to strip these before the article is emitted.
    """

    def __init__(
        self,
        feed_url: str = "https://feeds.bbci.co.uk/news/world/rss.xml",
        origin: str = "bbc_world",
        url_cleaner: Callable[[str], str] | None = None,
    ) -> None:
        self._feed_url = feed_url
        self._origin = origin
        self._url_cleaner = url_cleaner

    def _clean(self, url: str) -> str:
        """Apply the url_cleaner if one was provided, otherwise pass through."""
        if self._url_cleaner is not None:
            return self._url_cleaner(url)
        return url

    def origin_name(self) -> str:
        return self._origin

    def fetch(self) -> list[Article]:
        feed = feedparser.parse(self._feed_url)
        now = datetime.now(timezone.utc)
        articles = []

        for entry in feed.entries:
            url = self._clean(entry.get("link", ""))
            if not url:
                title = entry.get("title", "<no title>")
                logger.warning("Skipping entry with empty URL: %s", title)
                continue

            published = _parse_published(entry)
            article = Article(
                source="rss",
                origin=self.origin_name(),
                title=html.unescape(entry.get("title", "")),
                url=url,
                summary=html.unescape(entry.get("summary", "")),
                published=published,
                fetched_at=now,
            )
            articles.append(article)

        return articles


def _parse_published(entry: feedparser.FeedParserDict) -> datetime | None:
    """Extract publication datetime from an RSS entry.

    feedparser normalizes dates into a `published_parsed` time struct,
    but it can be None for entries without a date. Falls back to the raw
    `published` string via email.utils parsing (RSS uses RFC 2822 dates).
    """
    if entry.get("published_parsed"):
        # timegm (not mktime!) treats the struct as UTC — which is what
        # feedparser's published_parsed always is.  mktime would interpret
        # it as local time, producing wrong results outside UTC.
        return datetime.fromtimestamp(timegm(entry.published_parsed), tz=timezone.utc)

    raw = entry.get("published", "")
    if raw:
        try:
            return parsedate_to_datetime(raw)
        except (ValueError, TypeError):
            return None

    return None
