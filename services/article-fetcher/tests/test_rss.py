from unittest.mock import patch

import feedparser
import pytest

from article_fetcher import Article, DataFetcher, RssFetcher

# Canned RSS XML — standard RSS 2.0 structure
SAMPLE_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>BBC News - World</title>
    <link>https://www.bbc.co.uk/news/world</link>
    <item>
      <title>Iran and US reach preliminary agreement</title>
      <link>https://www.bbc.com/news/articles/iran-us-agreement-123</link>
      <description>Tehran and Washington announced a framework for talks.</description>
      <pubDate>Thu, 20 Mar 2026 14:30:00 GMT</pubDate>
    </item>
    <item>
      <title>OPEC meets to discuss output</title>
      <link>https://www.bbc.com/news/articles/opec-output-456</link>
      <description>Oil ministers gathered in Vienna.</description>
      <pubDate>Thu, 20 Mar 2026 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Article without a date</title>
      <link>https://www.bbc.com/news/articles/no-date-789</link>
      <description>This entry has no pubDate element.</description>
    </item>
  </channel>
</rss>
"""


@pytest.fixture
def parsed_feed() -> feedparser.FeedParserDict:
    """Parse the canned RSS XML into a feedparser result."""
    return feedparser.parse(SAMPLE_RSS)


@pytest.fixture
def fetcher(parsed_feed: feedparser.FeedParserDict) -> RssFetcher:
    """An RssFetcher that returns canned data instead of hitting the network."""
    f = RssFetcher()
    with patch.object(feedparser, "parse", return_value=parsed_feed):
        f._parsed = parsed_feed  # store for reference in tests
    return f


def _fetch_canned(fetcher: RssFetcher, parsed_feed: feedparser.FeedParserDict) -> list[Article]:
    """Call fetch() with feedparser.parse mocked to return canned data."""
    with patch.object(feedparser, "parse", return_value=parsed_feed):
        return fetcher.fetch()


class TestRssFetcherInterface:
    def test_is_data_fetcher(self) -> None:
        assert issubclass(RssFetcher, DataFetcher)

    def test_default_origin_name(self) -> None:
        fetcher = RssFetcher()
        assert fetcher.origin_name() == "bbc_world"

    def test_custom_origin_name(self) -> None:
        fetcher = RssFetcher(origin="ap")
        assert fetcher.origin_name() == "ap"

    def test_custom_feed_url(self) -> None:
        fetcher = RssFetcher(feed_url="https://example.com/feed.xml")
        assert fetcher._feed_url == "https://example.com/feed.xml"


class TestRssFetcherParsing:
    def test_returns_articles(
        self, fetcher: RssFetcher, parsed_feed: feedparser.FeedParserDict
    ) -> None:
        articles = _fetch_canned(fetcher, parsed_feed)
        assert isinstance(articles, list)
        # 3 items in sample RSS, all with valid links
        assert len(articles) == 3
        assert all(isinstance(a, Article) for a in articles)

    def test_article_fields(
        self, fetcher: RssFetcher, parsed_feed: feedparser.FeedParserDict
    ) -> None:
        articles = _fetch_canned(fetcher, parsed_feed)
        first = articles[0]
        assert first.source == "rss"
        assert first.origin == "bbc_world"
        assert first.title == "Iran and US reach preliminary agreement"
        assert first.url == "https://www.bbc.com/news/articles/iran-us-agreement-123"
        assert "Tehran" in first.summary
        assert first.published is not None
        assert first.fetched_at is not None

    def test_missing_pubdate_gives_none(
        self, fetcher: RssFetcher, parsed_feed: feedparser.FeedParserDict
    ) -> None:
        articles = _fetch_canned(fetcher, parsed_feed)
        no_date = articles[2]
        assert no_date.title == "Article without a date"
        assert no_date.published is None

    def test_all_articles_have_fetched_at(
        self, fetcher: RssFetcher, parsed_feed: feedparser.FeedParserDict
    ) -> None:
        articles = _fetch_canned(fetcher, parsed_feed)
        fetched_times = [a.fetched_at for a in articles]
        # All should have the same fetched_at (set once per fetch() call)
        assert all(t == fetched_times[0] for t in fetched_times)

    def test_empty_feed_returns_empty_list(self, fetcher: RssFetcher) -> None:
        empty_feed = feedparser.parse("<rss><channel></channel></rss>")
        with patch.object(feedparser, "parse", return_value=empty_feed):
            articles = fetcher.fetch()
        assert articles == []


class TestMissingFields:
    """RSS entries with missing or empty fields should be handled gracefully."""

    def test_entry_without_link_is_skipped(self, fetcher: RssFetcher) -> None:
        """Entries with no <link> element produce empty URLs — these should be dropped."""
        rss_no_link = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Linkless entry</title>
      <description>This item has no link element.</description>
    </item>
    <item>
      <title>Valid entry</title>
      <link>https://example.com/valid</link>
      <description>This one has a link.</description>
    </item>
  </channel>
</rss>
"""
        feed = feedparser.parse(rss_no_link)
        with patch.object(feedparser, "parse", return_value=feed):
            articles = fetcher.fetch()
        assert len(articles) == 1
        assert articles[0].url == "https://example.com/valid"

    def test_entry_with_empty_link_is_skipped(self, fetcher: RssFetcher) -> None:
        rss_empty_link = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Empty link</title>
      <link></link>
      <description>Link element is present but empty.</description>
    </item>
  </channel>
</rss>
"""
        feed = feedparser.parse(rss_empty_link)
        with patch.object(feedparser, "parse", return_value=feed):
            articles = fetcher.fetch()
        assert articles == []

    def test_entry_missing_title_gets_empty_string(self, fetcher: RssFetcher) -> None:
        rss_no_title = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <link>https://example.com/no-title</link>
      <description>No title here.</description>
    </item>
  </channel>
</rss>
"""
        feed = feedparser.parse(rss_no_title)
        with patch.object(feedparser, "parse", return_value=feed):
            articles = fetcher.fetch()
        assert len(articles) == 1
        assert articles[0].title == ""

    def test_entry_missing_summary_gets_empty_string(self, fetcher: RssFetcher) -> None:
        rss_no_summary = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>No summary</title>
      <link>https://example.com/no-summary</link>
    </item>
  </channel>
</rss>
"""
        feed = feedparser.parse(rss_no_summary)
        with patch.object(feedparser, "parse", return_value=feed):
            articles = fetcher.fetch()
        assert len(articles) == 1
        assert articles[0].summary == ""


class TestMalformedFeed:
    """feedparser is very tolerant of bad input, but we should still verify."""

    def test_garbage_xml_returns_empty(self, fetcher: RssFetcher) -> None:
        """feedparser returns an empty entries list for non-RSS content."""
        garbage_feed = feedparser.parse("this is not xml at all")
        with patch.object(feedparser, "parse", return_value=garbage_feed):
            articles = fetcher.fetch()
        assert articles == []

    def test_html_instead_of_rss_returns_empty(self, fetcher: RssFetcher) -> None:
        html_feed = feedparser.parse("<html><body>Not a feed</body></html>")
        with patch.object(feedparser, "parse", return_value=html_feed):
            articles = fetcher.fetch()
        assert articles == []


class TestAbcEnforcement:
    def test_cannot_instantiate_abstract_fetcher(self) -> None:
        """DataFetcher is abstract — instantiating it directly should fail."""
        with pytest.raises(TypeError):
            DataFetcher()  # type: ignore[abstract]
