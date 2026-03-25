"""Tests for __main__.py — the wiring between consumer, scraper, and publisher."""

from unittest.mock import MagicMock, patch

from article_scraper.__main__ import _REQUIRED_FIELDS, handle_message


def _make_valid_payload() -> dict:
    return {
        "source": "rss",
        "origin": "bbc_world",
        "title": "Test Article",
        "url": "https://example.com/test",
        "summary": "A summary.",
        "published": "2026-03-20T14:00:00+00:00",
        "fetched_at": "2026-03-20T14:30:00+00:00",
    }


class TestHandleMessage:
    @patch("article_scraper.__main__.scrape_article")
    def test_calls_scraper_with_rss_article(
        self, mock_scrape: MagicMock,
    ) -> None:
        """handle_message constructs an RssArticle and passes it to scraper."""
        mock_scrape.return_value = None
        publisher = MagicMock()

        handle_message(_make_valid_payload(), publisher)

        mock_scrape.assert_called_once()
        article = mock_scrape.call_args[0][0]
        assert article.url == "https://example.com/test"
        assert article.origin == "bbc_world"

    @patch("article_scraper.__main__.scrape_article")
    def test_publishes_on_successful_scrape(
        self, mock_scrape: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scrape.return_value = mock_result
        publisher = MagicMock()

        handle_message(_make_valid_payload(), publisher)

        publisher.publish.assert_called_once_with(mock_result)

    @patch("article_scraper.__main__.scrape_article")
    def test_skips_publish_when_scraper_returns_none(
        self, mock_scrape: MagicMock,
    ) -> None:
        mock_scrape.return_value = None
        publisher = MagicMock()

        handle_message(_make_valid_payload(), publisher)

        publisher.publish.assert_not_called()

    @patch("article_scraper.__main__.scrape_article")
    def test_missing_field_logs_error_and_returns(
        self, mock_scrape: MagicMock,
    ) -> None:
        """A payload missing a required field should not call the scraper."""
        publisher = MagicMock()
        payload = _make_valid_payload()
        del payload["title"]

        handle_message(payload, publisher)

        mock_scrape.assert_not_called()
        publisher.publish.assert_not_called()

    @patch("article_scraper.__main__.scrape_article")
    def test_all_required_fields_checked(
        self, mock_scrape: MagicMock,
    ) -> None:
        """Every field in _REQUIRED_FIELDS is validated."""
        publisher = MagicMock()

        for field in _REQUIRED_FIELDS:
            mock_scrape.reset_mock()
            payload = _make_valid_payload()
            del payload[field]

            handle_message(payload, publisher)
            mock_scrape.assert_not_called(), f"scraper called with {field} missing"

    @patch("article_scraper.__main__.scrape_article")
    def test_published_field_is_optional(
        self, mock_scrape: MagicMock,
    ) -> None:
        """'published' can be missing — it uses .get() with None default."""
        mock_scrape.return_value = None
        publisher = MagicMock()
        payload = _make_valid_payload()
        del payload["published"]

        handle_message(payload, publisher)

        mock_scrape.assert_called_once()
        article = mock_scrape.call_args[0][0]
        assert article.published is None


class TestMain:
    @patch("article_scraper.__main__.MessageConsumer")
    @patch("article_scraper.__main__.RabbitMqPublisher")
    @patch.dict("os.environ", {}, clear=True)
    def test_exits_when_rabbitmq_url_missing(
        self, mock_pub: MagicMock, mock_consumer: MagicMock,
    ) -> None:
        """main() should sys.exit(1) if RABBITMQ_URL is not set."""
        from article_scraper.__main__ import main

        try:
            main()
        except SystemExit as e:
            assert e.code == 1
        else:
            raise AssertionError("main() did not exit")

        mock_pub.assert_not_called()
        mock_consumer.assert_not_called()
