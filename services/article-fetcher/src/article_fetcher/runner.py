import logging
import time
from collections.abc import Callable

from article_fetcher.base import DataFetcher
from article_fetcher.dedup import InMemorySeenUrls, SeenUrls
from article_fetcher.models import Article

logger = logging.getLogger(__name__)


class FetchLoop:
    """Periodically fetches articles and skips already-seen ones.

    Wraps any DataFetcher with a timed loop and URL-based deduplication.
    Each new article is passed to the on_article callback — the caller
    decides what to do with it (log, publish to RabbitMQ, collect, etc.).

    Deduplication is delegated to a SeenUrls backend (Redis or in-memory).
    Pass one via the seen_urls parameter; defaults to InMemorySeenUrls.

    The optional sleep_fn parameter controls how the loop waits between
    cycles.  By default it uses time.sleep, but when paired with a
    RabbitMQ publisher you should pass publisher.sleep instead — this
    keeps the AMQP connection alive by processing heartbeat frames
    during the wait.
    """

    def __init__(
        self,
        fetcher: DataFetcher,
        on_article: Callable[[Article], None],
        interval_seconds: int = 900,
        sleep_fn: Callable[[float], None] | None = None,
        seen_urls: SeenUrls | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._on_article = on_article
        self._interval = interval_seconds
        self._sleep = sleep_fn if sleep_fn is not None else time.sleep
        self._seen_urls = seen_urls if seen_urls is not None else InMemorySeenUrls()

    def fetch_new(self) -> list[Article]:
        """Run one fetch cycle, deliver new articles to the callback.

        Calls the underlying fetcher, filters out URLs we've already seen,
        delivers each new article via on_article, and only marks it as seen
        after delivery succeeds.  If on_article raises for a particular
        article, that article is skipped (not marked seen) and will be
        retried next cycle.  Processing continues with the remaining articles.
        """
        articles = self._fetcher.fetch()
        new = [a for a in articles if not self._seen_urls.contains(a.url)]
        delivered: list[Article] = []
        for article in new:
            try:
                self._on_article(article)
                self._seen_urls.add(article.url)
                delivered.append(article)
            except Exception:
                logger.exception("Failed to deliver article %s, will retry next cycle", article.url)
        return delivered

    def run(self) -> None:
        """Fetch in a loop forever. Blocks the calling thread."""
        logger.info(
            "Starting fetch loop (source=%s, interval=%ds)",
            self._fetcher.origin_name(),
            self._interval,
        )
        while True:
            try:
                new_articles = self.fetch_new()
                logger.info(
                    "Cycle done: %d new article(s)",
                    len(new_articles),
                )
            except Exception:
                logger.exception("Fetch cycle failed, will retry next cycle")
            self._sleep(self._interval)
