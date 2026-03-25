from abc import ABC, abstractmethod

from article_fetcher.models import Article


class DataFetcher(ABC):
    """Abstract base class for article fetchers.

    Each concrete fetcher knows how to pull articles from one external source
    (RSS feed, API, etc.) and convert them into Article objects.

    Why ABC and not Protocol: we own all implementations, and ABC gives us
    runtime enforcement — forgetting to implement a method raises TypeError
    at instantiation, not silently at call time.
    """

    @abstractmethod
    def fetch(self) -> list[Article]:
        """Fetch the latest articles from this source."""
        ...

    @abstractmethod
    def origin_name(self) -> str:
        """Short identifier for the news outlet, e.g. 'bbc_world', 'ap'."""
        ...
