from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from article_fetcher import Article, DataFetcher, FetchLoop
from article_fetcher.dedup import MAX_SEEN_URLS, InMemorySeenUrls


class FakeFetcher(DataFetcher):
    """A stub fetcher that returns canned articles for testing."""

    def __init__(self, articles: list[Article]) -> None:
        self._articles = articles

    def origin_name(self) -> str:
        return "fake"

    def fetch(self) -> list[Article]:
        return list(self._articles)


def _make_article(title: str, url: str) -> Article:
    return Article(
        source="rss",
        origin="fake",
        title=title,
        url=url,
        summary="",
        published=None,
        fetched_at=datetime.now(timezone.utc),
    )


ARTICLE_A = _make_article("Article A", "https://example.com/a")
ARTICLE_B = _make_article("Article B", "https://example.com/b")
ARTICLE_C = _make_article("Article C", "https://example.com/c")


def _make_loop(
    fetcher: DataFetcher,
    sleep_fn: None | MagicMock = None,
    seen_urls: InMemorySeenUrls | None = None,
) -> tuple[FetchLoop, list[Article]]:
    """Create a FetchLoop with a collecting callback. Returns (loop, collected_list)."""
    collected: list[Article] = []
    if seen_urls is None:
        seen_urls = InMemorySeenUrls()
    loop = FetchLoop(
        fetcher, on_article=collected.append, sleep_fn=sleep_fn, seen_urls=seen_urls,
    )
    return loop, collected


class TestFetchNew:
    def test_returns_all_on_first_call(self) -> None:
        fetcher = FakeFetcher([ARTICLE_A, ARTICLE_B])
        loop, collected = _make_loop(fetcher)
        result = loop.fetch_new()
        assert len(result) == 2

    def test_skips_seen_urls_on_second_call(self) -> None:
        fetcher = FakeFetcher([ARTICLE_A, ARTICLE_B])
        loop, collected = _make_loop(fetcher)
        loop.fetch_new()
        result = loop.fetch_new()
        assert result == []

    def test_returns_only_new_articles_on_partial_overlap(self) -> None:
        fetcher = FakeFetcher([ARTICLE_A, ARTICLE_B])
        loop, collected = _make_loop(fetcher)
        loop.fetch_new()

        # Feed now has one old (A) and one new (C)
        fetcher._articles = [ARTICLE_A, ARTICLE_C]
        result = loop.fetch_new()
        assert len(result) == 1
        assert result[0].url == "https://example.com/c"

    def test_empty_fetch_returns_empty(self) -> None:
        fetcher = FakeFetcher([])
        loop, collected = _make_loop(fetcher)
        assert loop.fetch_new() == []

    def test_accepts_any_data_fetcher(self) -> None:
        """FetchLoop takes the abstract DataFetcher, not a concrete class."""
        fetcher = FakeFetcher([ARTICLE_A])
        loop, collected = _make_loop(fetcher)
        assert loop.fetch_new()[0].origin == "fake"


class TestCallback:
    def test_callback_receives_new_articles(self) -> None:
        fetcher = FakeFetcher([ARTICLE_A, ARTICLE_B])
        loop, collected = _make_loop(fetcher)
        loop.fetch_new()
        assert len(collected) == 2
        assert collected[0].url == "https://example.com/a"
        assert collected[1].url == "https://example.com/b"

    def test_callback_not_called_for_seen_articles(self) -> None:
        fetcher = FakeFetcher([ARTICLE_A])
        loop, collected = _make_loop(fetcher)
        loop.fetch_new()
        loop.fetch_new()
        assert len(collected) == 1

    def test_callback_called_only_for_new_on_overlap(self) -> None:
        fetcher = FakeFetcher([ARTICLE_A, ARTICLE_B])
        loop, collected = _make_loop(fetcher)
        loop.fetch_new()

        fetcher._articles = [ARTICLE_A, ARTICLE_C]
        loop.fetch_new()
        assert len(collected) == 3  # A, B from first call + C from second
        assert collected[2].url == "https://example.com/c"


class TestSleepFn:
    """Tests for the pluggable sleep function."""

    def test_defaults_to_time_sleep(self) -> None:
        """When no sleep_fn is provided, FetchLoop uses time.sleep."""
        fetcher = FakeFetcher([])
        loop = FetchLoop(fetcher, on_article=lambda a: None)
        import time

        assert loop._sleep is time.sleep

    def test_custom_sleep_fn_is_used(self) -> None:
        """When a sleep_fn is provided, FetchLoop uses it instead of time.sleep."""
        custom_sleep = MagicMock()
        fetcher = FakeFetcher([])
        loop = FetchLoop(fetcher, on_article=lambda a: None, sleep_fn=custom_sleep)
        assert loop._sleep is custom_sleep

    @patch("article_fetcher.runner.time.sleep")
    def test_run_calls_custom_sleep_not_time_sleep(self, mock_time_sleep: MagicMock) -> None:
        """The run loop uses the custom sleep_fn, not time.sleep."""
        custom_sleep = MagicMock()
        # Make the custom sleep raise after one call to stop the infinite loop.
        custom_sleep.side_effect = [None, KeyboardInterrupt]

        fetcher = FakeFetcher([])
        loop = FetchLoop(
            fetcher,
            on_article=lambda a: None,
            interval_seconds=30,
            sleep_fn=custom_sleep,
        )

        try:
            loop.run()
        except KeyboardInterrupt:
            pass

        # Custom sleep should have been called with the interval.
        custom_sleep.assert_called_with(30)
        # time.sleep should NOT have been called.
        mock_time_sleep.assert_not_called()


class TestRunErrorHandling:
    """The run loop should survive exceptions from fetch_new."""

    def test_run_continues_after_fetch_error(self) -> None:
        """A network error in one cycle should not kill the loop."""
        fetcher = FakeFetcher([])
        # Make fetch() raise on the first call, then return normally.
        fetcher.fetch = MagicMock(  # type: ignore[method-assign]
            side_effect=[ConnectionError("DNS failure"), []]
        )
        sleep = MagicMock(side_effect=[None, KeyboardInterrupt])
        loop = FetchLoop(fetcher, on_article=lambda a: None, sleep_fn=sleep)

        try:
            loop.run()
        except KeyboardInterrupt:
            pass

        # fetch was called twice — once errored, once succeeded.
        assert fetcher.fetch.call_count == 2
        # sleep was called after both cycles (including the failed one).
        assert sleep.call_count == 2


class TestPerArticleFailure:
    """on_article failure for one article should not lose the rest."""

    def test_failed_article_not_marked_seen(self) -> None:
        """If on_article raises, the URL is NOT marked seen — it will be retried."""
        fetcher = FakeFetcher([ARTICLE_A, ARTICLE_B])
        callback = MagicMock(side_effect=[RuntimeError("publish failed"), None])
        seen = InMemorySeenUrls()
        loop = FetchLoop(fetcher, on_article=callback, seen_urls=seen)

        result = loop.fetch_new()

        # Only B was delivered successfully.
        assert len(result) == 1
        assert result[0].url == "https://example.com/b"
        # A is NOT marked seen — it will be retried next cycle.
        assert not seen.contains("https://example.com/a")
        # B IS marked seen.
        assert seen.contains("https://example.com/b")

    def test_failed_article_retried_next_cycle(self) -> None:
        """A failed article reappears in the next cycle's results."""
        fetcher = FakeFetcher([ARTICLE_A, ARTICLE_B])
        call_count = 0

        def flaky_callback(article: Article) -> None:
            nonlocal call_count
            call_count += 1
            # Fail on the very first call (A, first cycle), succeed after.
            if call_count == 1:
                raise RuntimeError("transient failure")

        seen = InMemorySeenUrls()
        loop = FetchLoop(fetcher, on_article=flaky_callback, seen_urls=seen)

        # Cycle 1: A fails, B succeeds.
        result1 = loop.fetch_new()
        assert len(result1) == 1
        assert result1[0].url == "https://example.com/b"

        # Cycle 2: A is retried and succeeds, B is skipped (already seen).
        result2 = loop.fetch_new()
        assert len(result2) == 1
        assert result2[0].url == "https://example.com/a"

    def test_remaining_articles_still_delivered_after_failure(self) -> None:
        """A failure mid-batch does not abort processing of later articles."""
        fetcher = FakeFetcher([ARTICLE_A, ARTICLE_B, ARTICLE_C])
        callback = MagicMock(
            side_effect=[None, RuntimeError("B fails"), None]
        )
        seen = InMemorySeenUrls()
        loop = FetchLoop(fetcher, on_article=callback, seen_urls=seen)

        result = loop.fetch_new()
        # A and C delivered, B failed.
        assert len(result) == 2
        assert result[0].url == "https://example.com/a"
        assert result[1].url == "https://example.com/c"


class TestInMemorySeenUrlsCap:
    """The InMemorySeenUrls backend should not grow without bound."""

    def test_evicts_oldest_when_cap_reached(self) -> None:
        seen = InMemorySeenUrls(max_size=100)
        for i in range(110):
            seen.add(f"https://example.com/{i}")

        # First 10 should have been evicted
        assert not seen.contains("https://example.com/0")
        assert not seen.contains("https://example.com/9")
        # Latest should still be present
        assert seen.contains("https://example.com/109")

    def test_default_max_size(self) -> None:
        seen = InMemorySeenUrls()
        assert seen._max_size == MAX_SEEN_URLS
