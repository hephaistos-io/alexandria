"""Tests for the log_streamer module — parsing and formatting logic.

We test the pure helper functions (_parse_log_line, _wrap_raw, _parse_docker_ts)
in isolation. These don't need Docker or asyncio, so they're fast and simple.

For the async LogStreamer class itself, the integration test in test_server.py
covers the WebSocket endpoint end-to-end using a mock.
"""

from monitoring_api.log_streamer import _parse_docker_ts, _parse_log_line, _wrap_raw

# ---------------------------------------------------------------------------
# _parse_docker_ts
# ---------------------------------------------------------------------------


def test_parse_docker_ts_standard():
    """Parses a Docker nanosecond timestamp into our clean ISO 8601 format."""
    result = _parse_docker_ts("2026-03-21T10:15:30.123456789Z")
    assert result == "2026-03-21T10:15:30Z"


def test_parse_docker_ts_no_subsecond():
    """Works when the timestamp has no fractional seconds."""
    result = _parse_docker_ts("2026-03-21T10:15:30Z")
    assert result == "2026-03-21T10:15:30Z"


def test_parse_docker_ts_empty():
    """Returns None for an empty string."""
    assert _parse_docker_ts("") is None


def test_parse_docker_ts_garbage():
    """Returns None for an unparseable string without crashing."""
    assert _parse_docker_ts("not-a-timestamp") is None


# ---------------------------------------------------------------------------
# _wrap_raw
# ---------------------------------------------------------------------------


def test_wrap_raw_basic():
    """Wraps a plain text line in the standard envelope."""
    result = _wrap_raw("some log line", "article-fetcher", "2026-03-21T10:00:00.000Z")
    assert result["message"] == "some log line"
    assert result["service"] == "article-fetcher"
    assert result["level"] == "info"
    assert result["ts"] == "2026-03-21T10:00:00Z"


def test_wrap_raw_uses_fallback_ts_when_docker_ts_invalid():
    """Falls back to current time when Docker timestamp is unparseable."""
    result = _wrap_raw("hello", "my-service", "bad-ts")
    # We just check the ts field is present and looks like an ISO timestamp.
    assert "T" in result["ts"]
    assert result["ts"].endswith("Z")


# ---------------------------------------------------------------------------
# _parse_log_line
# ---------------------------------------------------------------------------


def test_parse_log_line_valid_json():
    """Passes through a valid JSON log line from our JsonFormatter."""
    line = (
        '{"ts": "2026-03-21T10:00:00Z", "level": "info",'
        ' "service": "article-fetcher", "logger": "article_fetcher.runner",'
        ' "message": "Fetched 10 articles"}'
    )
    result = _parse_log_line(line, "article-fetcher", "2026-03-21T10:00:00.000Z")
    assert result["message"] == "Fetched 10 articles"
    assert result["level"] == "info"
    assert result["logger"] == "article_fetcher.runner"


def test_parse_log_line_plain_text():
    """Wraps a plain text line (e.g. from a third-party library) in an envelope."""
    result = _parse_log_line(
        "Starting server on port 5672", "rabbitmq", "2026-03-21T10:00:00.000Z"
    )
    assert result["message"] == "Starting server on port 5672"
    assert result["service"] == "rabbitmq"
    assert result["level"] == "info"


def test_parse_log_line_json_without_message_field():
    """JSON that doesn't have a 'message' field is treated as raw text."""
    line = '{"foo": "bar"}'
    result = _parse_log_line(line, "some-service", "2026-03-21T10:00:00.000Z")
    # Should be wrapped since no "message" key.
    assert result["service"] == "some-service"
    assert result["message"] == line


def test_parse_log_line_empty_string():
    """Empty line is wrapped without crashing."""
    result = _parse_log_line("", "my-service", "2026-03-21T10:00:00.000Z")
    assert result["service"] == "my-service"
    assert result["message"] == ""


def test_parse_log_line_json_array():
    """A JSON array (not an object) is treated as raw text."""
    line = '[1, 2, 3]'
    result = _parse_log_line(line, "svc", "2026-03-21T10:00:00.000Z")
    assert result["message"] == line
