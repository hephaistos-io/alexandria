from datetime import datetime, timezone

from article_fetcher import Article


class TestArticle:
    def test_create_with_all_fields(self) -> None:
        now = datetime.now(timezone.utc)
        article = Article(
            source="rss",
            origin="test",
            title="Test Article",
            url="https://example.com/article",
            summary="A test article summary.",
            published=now,
            fetched_at=now,
        )
        assert article.source == "rss"
        assert article.origin == "test"
        assert article.title == "Test Article"
        assert article.url == "https://example.com/article"
        assert article.summary == "A test article summary."
        assert article.published == now
        assert article.fetched_at == now

    def test_published_can_be_none(self) -> None:
        now = datetime.now(timezone.utc)
        article = Article(
            source="rss",
            origin="test",
            title="No Date",
            url="https://example.com",
            summary="",
            published=None,
            fetched_at=now,
        )
        assert article.published is None
