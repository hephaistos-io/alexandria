"""Tests for label_updater — classification result handling and DB writes."""

from unittest.mock import MagicMock, patch

from article_store.label_updater import LabelWriter, handle_message


def _make_valid_payload() -> dict:
    return {
        "url": "https://example.com/article-1",
        "labels": [
            {"name": "CONFLICT", "score": 0.85},
            {"name": "POLITICS", "score": 0.42},
        ],
        "classified_at": "2026-03-21T10:00:00Z",
    }


@patch("article_store.label_updater.psycopg.connect")
class TestLabelWriter:
    def test_update_returns_true_when_row_updated(
        self, mock_connect: MagicMock,
    ) -> None:
        mock_conn = mock_connect.return_value
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_conn.cursor.return_value.__enter__ = MagicMock(
            return_value=mock_cursor,
        )
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        writer = LabelWriter("postgresql://localhost/test")
        result = writer.update_automatic_labels(
            "https://example.com/a", ["CONFLICT"], "2026-03-21T10:00:00Z",
        )

        assert result is True
        mock_conn.commit.assert_called()

    def test_update_returns_false_when_url_not_found(
        self, mock_connect: MagicMock,
    ) -> None:
        mock_conn = mock_connect.return_value
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 0
        mock_conn.cursor.return_value.__enter__ = MagicMock(
            return_value=mock_cursor,
        )
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        writer = LabelWriter("postgresql://localhost/test")
        result = writer.update_automatic_labels(
            "https://example.com/missing", ["CONFLICT"], "2026-03-21T10:00:00Z",
        )

        assert result is False

    def test_update_passes_entities_as_json(
        self, mock_connect: MagicMock,
    ) -> None:
        mock_conn = mock_connect.return_value
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_conn.cursor.return_value.__enter__ = MagicMock(
            return_value=mock_cursor,
        )
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        entities = [{"name": "Iran", "type": "GPE"}]
        writer = LabelWriter("postgresql://localhost/test")
        writer.update_automatic_labels(
            "https://example.com/a", ["CONFLICT"], "2026-03-21T10:00:00Z",
            entities=entities,
        )

        # The entities param (3rd positional) should be JSON-encoded.
        call_args = mock_cursor.execute.call_args[0]
        params = call_args[1]
        assert '"Iran"' in params[2]

    def test_close_closes_connection(self, mock_connect: MagicMock) -> None:
        mock_conn = mock_connect.return_value
        mock_conn.closed = False

        writer = LabelWriter("postgresql://localhost/test")
        writer.close()

        mock_conn.close.assert_called_once()


class TestHandleMessage:
    def test_valid_payload_calls_writer(self) -> None:
        writer = MagicMock()
        writer.update_automatic_labels.return_value = True

        handle_message(_make_valid_payload(), writer)

        writer.update_automatic_labels.assert_called_once_with(
            "https://example.com/article-1",
            ["CONFLICT", "POLITICS"],
            "2026-03-21T10:00:00Z",
            None,
        )

    def test_missing_url_skips_processing(self) -> None:
        writer = MagicMock()

        handle_message({"labels": [], "classified_at": ""}, writer)

        writer.update_automatic_labels.assert_not_called()

    def test_empty_url_skips_processing(self) -> None:
        writer = MagicMock()

        handle_message({"url": "", "labels": [], "classified_at": ""}, writer)

        writer.update_automatic_labels.assert_not_called()

    def test_malformed_label_entry_skipped(self) -> None:
        """A label dict missing 'name' is skipped, others still processed."""
        writer = MagicMock()
        writer.update_automatic_labels.return_value = True

        payload = {
            "url": "https://example.com/a",
            "labels": [
                {"name": "CONFLICT", "score": 0.9},
                {"score": 0.5},  # missing "name"
                "just_a_string",  # not a dict
            ],
            "classified_at": "2026-03-21T10:00:00Z",
        }
        handle_message(payload, writer)

        # Only "CONFLICT" should survive validation.
        call_args = writer.update_automatic_labels.call_args
        assert call_args[0][1] == ["CONFLICT"]

    def test_entities_passed_through(self) -> None:
        writer = MagicMock()
        writer.update_automatic_labels.return_value = True

        payload = _make_valid_payload()
        payload["entities"] = [{"name": "Iran", "type": "GPE"}]

        handle_message(payload, writer)

        call_args = writer.update_automatic_labels.call_args
        assert call_args[0][3] == [{"name": "Iran", "type": "GPE"}]

    def test_missing_labels_key_defaults_to_empty(self) -> None:
        writer = MagicMock()
        writer.update_automatic_labels.return_value = True

        payload = {
            "url": "https://example.com/a",
            "classified_at": "2026-03-21T10:00:00Z",
        }
        handle_message(payload, writer)

        call_args = writer.update_automatic_labels.call_args
        assert call_args[0][1] == []
