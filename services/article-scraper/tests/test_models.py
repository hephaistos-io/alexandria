from article_scraper.models import RssArticle, ScrapedArticle


class TestRssArticle:
    def test_create(self) -> None:
        article = RssArticle(
            source="rss",
            origin="bbc_world",
            title="Test",
            url="https://example.com/test",
            summary="A summary.",
            published="2026-03-20T14:00:00+00:00",
            fetched_at="2026-03-20T14:30:00+00:00",
        )
        assert article.title == "Test"
        assert article.published == "2026-03-20T14:00:00+00:00"

    def test_published_can_be_none(self) -> None:
        article = RssArticle(
            source="rss",
            origin="bbc_world",
            title="No Date",
            url="https://example.com",
            summary="",
            published=None,
            fetched_at="2026-03-20T14:30:00+00:00",
        )
        assert article.published is None


class TestScrapedArticle:
    def test_create(self) -> None:
        article = ScrapedArticle(
            source="rss",
            origin="bbc_world",
            title="Test",
            url="https://example.com/test",
            summary="A summary.",
            published="2026-03-20T14:00:00+00:00",
            fetched_at="2026-03-20T14:30:00+00:00",
            content="Full article text here.",
            scraped_at="2026-03-20T14:31:00+00:00",
        )
        assert article.content == "Full article text here."
        assert article.scraped_at == "2026-03-20T14:31:00+00:00"
