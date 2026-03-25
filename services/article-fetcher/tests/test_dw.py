"""Tests for the Deutsche Welle source module."""

from unittest.mock import patch

import feedparser
import pytest

from article_fetcher import RssFetcher
from article_fetcher.sources.dw import FEED_URL, SOURCE_NAME, clean_url

# Canned RSS 1.0 (RDF) XML mimicking DW's actual feed structure.
# Key trait: ?maca=... tracking parameter on every link.
SAMPLE_DW_RDF = """\
<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://purl.org/rss/1.0/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>World | Deutsche Welle</title>
    <link>https://www.dw.com/english/</link>
    <description>World news from DW</description>
  </channel>
  <item rdf:about="https://www.dw.com/en/adrift-russian-tanker/a-12345?maca=en-rss-en-world-4025-rdf">
    <title>Adrift Russian tanker risks disaster</title>
    <link>https://www.dw.com/en/adrift-russian-tanker/a-12345?maca=en-rss-en-world-4025-rdf</link>
    <description>A damaged tanker drifts in the Mediterranean.</description>
    <dc:date>2026-03-22T12:00:00Z</dc:date>
  </item>
  <item rdf:about="https://www.dw.com/en/cuba-blackout/a-67890?maca=en-rss-en-world-4025-rdf">
    <title>Cuba hit by second blackout</title>
    <link>https://www.dw.com/en/cuba-blackout/a-67890?maca=en-rss-en-world-4025-rdf</link>
    <description>Island-wide power outage for the second time.</description>
    <dc:date>2026-03-22T10:30:00Z</dc:date>
  </item>
</rdf:RDF>
"""


class TestSourceConstants:
    def test_source_name(self) -> None:
        assert SOURCE_NAME == "dw_world"

    def test_feed_url_is_valid_https(self) -> None:
        assert FEED_URL.startswith("https://")

    def test_feed_url_points_to_dw(self) -> None:
        assert "dw.com" in FEED_URL or "rss.dw.com" in FEED_URL


class TestCleanUrl:
    def test_strips_maca_param(self) -> None:
        url = "https://www.dw.com/en/some-article/a-12345?maca=en-rss-en-world-4025-rdf"
        assert clean_url(url) == "https://www.dw.com/en/some-article/a-12345"

    def test_preserves_url_without_tracking(self) -> None:
        url = "https://www.dw.com/en/some-article/a-12345"
        assert clean_url(url) == "https://www.dw.com/en/some-article/a-12345"

    def test_preserves_other_query_params(self) -> None:
        url = "https://www.dw.com/en/example?page=2&maca=en-rss-en-world-4025-rdf"
        result = clean_url(url)
        assert "page=2" in result
        assert "maca" not in result

    def test_empty_query_after_stripping(self) -> None:
        url = "https://www.dw.com/en/example?maca=en-rss-en-world-4025-rdf"
        result = clean_url(url)
        assert "?" not in result


class TestRssFetcherWithDw:
    """Verify that RssFetcher + url_cleaner works with DW's RDF feed."""

    @pytest.fixture
    def parsed_feed(self) -> feedparser.FeedParserDict:
        return feedparser.parse(SAMPLE_DW_RDF)

    @pytest.fixture
    def fetcher(self) -> RssFetcher:
        return RssFetcher(feed_url=FEED_URL, origin=SOURCE_NAME, url_cleaner=clean_url)

    def test_origin_is_dw(self, fetcher: RssFetcher) -> None:
        assert fetcher.origin_name() == "dw_world"

    def test_parses_rdf_entries(
        self, fetcher: RssFetcher, parsed_feed: feedparser.FeedParserDict
    ) -> None:
        with patch.object(feedparser, "parse", return_value=parsed_feed):
            articles = fetcher.fetch()
        assert len(articles) == 2

    def test_urls_are_cleaned(
        self, fetcher: RssFetcher, parsed_feed: feedparser.FeedParserDict
    ) -> None:
        with patch.object(feedparser, "parse", return_value=parsed_feed):
            articles = fetcher.fetch()
        for article in articles:
            assert "maca=" not in article.url
            assert "dw.com" in article.url

    def test_article_fields(
        self, fetcher: RssFetcher, parsed_feed: feedparser.FeedParserDict
    ) -> None:
        with patch.object(feedparser, "parse", return_value=parsed_feed):
            articles = fetcher.fetch()
        first = articles[0]
        assert first.source == "rss"
        assert first.origin == "dw_world"
        assert first.title == "Adrift Russian tanker risks disaster"
        assert first.url == "https://www.dw.com/en/adrift-russian-tanker/a-12345"
