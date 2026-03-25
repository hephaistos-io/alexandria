"""Tests for the dedup backends (InMemorySeenUrls and RedisSeenUrls)."""

from unittest.mock import MagicMock, patch

from article_fetcher.dedup import InMemorySeenUrls, RedisSeenUrls


class TestInMemorySeenUrls:
    def test_add_and_contains(self) -> None:
        seen = InMemorySeenUrls()
        assert not seen.contains("https://example.com/a")
        seen.add("https://example.com/a")
        assert seen.contains("https://example.com/a")

    def test_unknown_url_returns_false(self) -> None:
        seen = InMemorySeenUrls()
        assert not seen.contains("https://example.com/unknown")

    def test_eviction_at_capacity(self) -> None:
        seen = InMemorySeenUrls(max_size=3)
        seen.add("https://example.com/1")
        seen.add("https://example.com/2")
        seen.add("https://example.com/3")
        seen.add("https://example.com/4")  # evicts /1

        assert not seen.contains("https://example.com/1")
        assert seen.contains("https://example.com/2")
        assert seen.contains("https://example.com/4")


@patch("article_fetcher.dedup.redis")
class TestRedisSeenUrls:
    """Test RedisSeenUrls with a mocked redis module."""

    def test_contains_calls_exists(self, mock_redis: MagicMock) -> None:
        mock_client = MagicMock()
        mock_redis.from_url.return_value = mock_client
        mock_client.exists.return_value = 1

        seen = RedisSeenUrls("redis://localhost:6379/0", origin="bbc_world")
        assert seen.contains("https://example.com/a")
        mock_client.exists.assert_called_once_with(
            "seen:bbc_world:https://example.com/a"
        )

    def test_contains_false_when_key_missing(self, mock_redis: MagicMock) -> None:
        mock_client = MagicMock()
        mock_redis.from_url.return_value = mock_client
        mock_client.exists.return_value = 0

        seen = RedisSeenUrls("redis://localhost:6379/0", origin="test")
        assert not seen.contains("https://example.com/a")

    def test_add_uses_set_with_ex(self, mock_redis: MagicMock) -> None:
        mock_client = MagicMock()
        mock_redis.from_url.return_value = mock_client

        seen = RedisSeenUrls("redis://localhost:6379/0", origin="test")
        seen.add("https://example.com/a")

        mock_client.set.assert_called_once_with(
            "seen:test:https://example.com/a", "1", ex=7 * 24 * 60 * 60,
        )

    def test_contains_returns_false_on_redis_error(self, mock_redis: MagicMock) -> None:
        mock_client = MagicMock()
        mock_redis.from_url.return_value = mock_client
        mock_redis.RedisError = Exception  # so `except redis.RedisError` catches it
        mock_client.exists.side_effect = Exception("connection refused")

        seen = RedisSeenUrls("redis://localhost:6379/0", origin="test")
        assert not seen.contains("https://example.com/a")

    def test_add_does_not_raise_on_redis_error(self, mock_redis: MagicMock) -> None:
        mock_client = MagicMock()
        mock_redis.from_url.return_value = mock_client
        mock_redis.RedisError = Exception
        mock_client.set.side_effect = Exception("connection refused")

        seen = RedisSeenUrls("redis://localhost:6379/0", origin="test")
        # Should not raise
        seen.add("https://example.com/a")

    def test_key_prefix_scoped_to_origin(self, mock_redis: MagicMock) -> None:
        mock_redis.from_url.return_value = MagicMock()
        seen = RedisSeenUrls("redis://localhost:6379/0", origin="aljazeera")
        assert seen._prefix == "seen:aljazeera:"

    def test_ping_called_at_init(self, mock_redis: MagicMock) -> None:
        mock_client = MagicMock()
        mock_redis.from_url.return_value = mock_client

        RedisSeenUrls("redis://localhost:6379/0", origin="test")
        mock_client.ping.assert_called_once()

    def test_init_logs_error_on_failed_ping(self, mock_redis: MagicMock) -> None:
        mock_client = MagicMock()
        mock_redis.from_url.return_value = mock_client
        mock_redis.RedisError = Exception
        mock_client.ping.side_effect = Exception("unreachable")

        # Should not raise — just logs an error
        seen = RedisSeenUrls("redis://localhost:6379/0", origin="test")
        assert seen._prefix == "seen:test:"
