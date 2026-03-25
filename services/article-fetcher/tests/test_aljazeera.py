"""Tests for the Al Jazeera source module."""

from unittest.mock import patch

import feedparser
import pytest

from article_fetcher import RssFetcher
from article_fetcher.sources.aljazeera import FEED_URL, SOURCE_NAME, clean_url

# Canned RSS XML mimicking Al Jazeera's actual feed structure.
# Key traits: CDATA descriptions, ?traffic_source=rss on links, <category> tags.
SAMPLE_ALJAZEERA_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Al Jazeera - Breaking News, World News and Video from Al Jazeera</title>
    <link>https://www.aljazeera.com</link>
    <description>Breaking News, World News and Video from Al Jazeera</description>
    <language>en</language>
    <item>
      <link>https://www.aljazeera.com/news/2026/3/21/example-article?traffic_source=rss</link>
      <title>Example breaking news article</title>
      <description><![CDATA[An example description with HTML entities.]]></description>
      <pubDate>Sat, 21 Mar 2026 14:30:00 +0000</pubDate>
      <category>News</category>
    </item>
    <item>
      <link>https://www.aljazeera.com/opinions/2026/3/21/opinion-piece?traffic_source=rss</link>
      <title>An opinion piece</title>
      <description><![CDATA[Opinion content from a columnist.]]></description>
      <pubDate>Sat, 21 Mar 2026 12:00:00 +0000</pubDate>
      <category>Opinions</category>
    </item>
    <item>
      <link>https://www.aljazeera.com/news/2026/3/21/no-date-article?traffic_source=rss</link>
      <title>Article without a publication date</title>
      <description><![CDATA[This entry has no pubDate.]]></description>
    </item>
  </channel>
</rss>
"""


class TestSourceConstants:
    def test_source_name(self) -> None:
        assert SOURCE_NAME == "aljazeera"

    def test_feed_url_is_valid_https(self) -> None:
        assert FEED_URL.startswith("https://")

    def test_feed_url_points_to_aljazeera(self) -> None:
        assert "aljazeera.com" in FEED_URL


class TestCleanUrl:
    def test_strips_traffic_source_param(self) -> None:
        url = "https://www.aljazeera.com/news/2026/3/21/example?traffic_source=rss"
        assert clean_url(url) == "https://www.aljazeera.com/news/2026/3/21/example"

    def test_preserves_url_without_tracking(self) -> None:
        url = "https://www.aljazeera.com/news/2026/3/21/example"
        assert clean_url(url) == "https://www.aljazeera.com/news/2026/3/21/example"

    def test_preserves_other_query_params(self) -> None:
        url = "https://www.aljazeera.com/news/example?page=2&traffic_source=rss"
        result = clean_url(url)
        assert "page=2" in result
        assert "traffic_source" not in result

    def test_empty_query_after_stripping(self) -> None:
        """When traffic_source is the only param, the result has no query string."""
        url = "https://www.aljazeera.com/news/example?traffic_source=rss"
        result = clean_url(url)
        assert "?" not in result


class TestRssFetcherWithAlJazeera:
    """Verify that the generic RssFetcher works correctly with Al Jazeera config."""

    @pytest.fixture
    def parsed_feed(self) -> feedparser.FeedParserDict:
        return feedparser.parse(SAMPLE_ALJAZEERA_RSS)

    @pytest.fixture
    def fetcher(self) -> RssFetcher:
        return RssFetcher(feed_url=FEED_URL, origin=SOURCE_NAME, url_cleaner=clean_url)

    def test_origin_is_aljazeera(self, fetcher: RssFetcher) -> None:
        assert fetcher.origin_name() == "aljazeera"

    def test_parses_all_entries(
        self, fetcher: RssFetcher, parsed_feed: feedparser.FeedParserDict
    ) -> None:
        with patch.object(feedparser, "parse", return_value=parsed_feed):
            articles = fetcher.fetch()
        assert len(articles) == 3

    def test_article_fields(
        self, fetcher: RssFetcher, parsed_feed: feedparser.FeedParserDict
    ) -> None:
        with patch.object(feedparser, "parse", return_value=parsed_feed):
            articles = fetcher.fetch()
        first = articles[0]
        assert first.source == "rss"
        assert first.origin == "aljazeera"
        assert first.title == "Example breaking news article"
        assert "aljazeera.com" in first.url
        assert first.published is not None
        assert first.fetched_at is not None

    def test_urls_are_cleaned(
        self, fetcher: RssFetcher, parsed_feed: feedparser.FeedParserDict
    ) -> None:
        with patch.object(feedparser, "parse", return_value=parsed_feed):
            articles = fetcher.fetch()
        for article in articles:
            assert "traffic_source" not in article.url

    def test_cdata_description_parsed(
        self, fetcher: RssFetcher, parsed_feed: feedparser.FeedParserDict
    ) -> None:
        with patch.object(feedparser, "parse", return_value=parsed_feed):
            articles = fetcher.fetch()
        # feedparser strips CDATA wrappers and decodes entities
        assert "example description" in articles[0].summary.lower()

    def test_missing_pubdate_gives_none(
        self, fetcher: RssFetcher, parsed_feed: feedparser.FeedParserDict
    ) -> None:
        with patch.object(feedparser, "parse", return_value=parsed_feed):
            articles = fetcher.fetch()
        assert articles[2].published is None
