from unittest.mock import patch

from article_scraper.models import RssArticle
from article_scraper.scraper import scrape_article

# Minimal HTML that trafilatura can extract from.
SAMPLE_HTML = """\
<html>
<head><title>Test Article</title></head>
<body>
<article>
<h1>Iran and US reach preliminary agreement</h1>
<p>Tehran and Washington announced a framework for nuclear talks on Thursday,
marking the first direct diplomatic engagement in over a year. The agreement,
brokered with European mediators, outlines a timeline for sanctions relief
in exchange for enhanced inspections of nuclear facilities.</p>
<p>Senior officials from both sides described the talks as productive, though
cautioned that significant hurdles remain before a final deal can be reached.
The framework sets a six-month negotiating window.</p>
</article>
<footer>Copyright BBC 2026</footer>
</body>
</html>
"""


def _make_rss_article() -> RssArticle:
    return RssArticle(
        source="rss",
        origin="bbc_world",
        title="Iran and US reach preliminary agreement",
        url="https://www.bbc.com/news/articles/iran-us-123",
        summary="Tehran and Washington announced a framework for talks.",
        published="2026-03-20T14:30:00+00:00",
        fetched_at="2026-03-20T14:30:00+00:00",
    )


class TestScrapeArticle:
    @patch("article_scraper.scraper.fetch_url")
    def test_successful_extraction(self, mock_fetch) -> None:
        mock_fetch.return_value = SAMPLE_HTML
        result = scrape_article(_make_rss_article())
        assert result is not None
        assert result.content  # non-empty string
        assert "Tehran" in result.content or "framework" in result.content
        assert result.scraped_at  # timestamp populated

    @patch("article_scraper.scraper.fetch_url")
    def test_fetch_returns_none(self, mock_fetch) -> None:
        """404 or network error — fetch_url returns None."""
        mock_fetch.return_value = None
        result = scrape_article(_make_rss_article())
        assert result is None

    @patch("article_scraper.scraper.extract")
    @patch("article_scraper.scraper.fetch_url")
    def test_extract_returns_none(self, mock_fetch, mock_extract) -> None:
        """Page fetched but trafilatura can't extract content."""
        mock_fetch.return_value = "<html><body>Login required</body></html>"
        mock_extract.return_value = None
        result = scrape_article(_make_rss_article())
        assert result is None

    @patch("article_scraper.scraper.extract")
    @patch("article_scraper.scraper.fetch_url")
    def test_extract_returns_empty_string(self, mock_fetch, mock_extract) -> None:
        mock_fetch.return_value = "<html><body></body></html>"
        mock_extract.return_value = ""
        result = scrape_article(_make_rss_article())
        assert result is None

    @patch("article_scraper.scraper.fetch_url")
    def test_preserves_original_fields(self, mock_fetch) -> None:
        mock_fetch.return_value = SAMPLE_HTML
        article = _make_rss_article()
        result = scrape_article(article)
        assert result is not None
        assert result.source == article.source
        assert result.origin == article.origin
        assert result.title == article.title
        assert result.url == article.url
        assert result.summary == article.summary
        assert result.published == article.published
        assert result.fetched_at == article.fetched_at

    @patch("article_scraper.scraper.fetch_url")
    def test_favor_recall_not_set(self, mock_fetch) -> None:
        """favor_recall was dropped — it inflated content with nav/footer junk."""
        mock_fetch.return_value = SAMPLE_HTML
        with patch("article_scraper.scraper.extract") as mock_extract:
            mock_extract.return_value = "some content"
            scrape_article(_make_rss_article())
            mock_extract.assert_called_once()
            _, kwargs = mock_extract.call_args
            assert "favor_recall" not in kwargs
