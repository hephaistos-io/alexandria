from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from ucdp_fetcher.fetcher import UcdpFetcher


def _make_raw_item(
    id_=123,
    lat=34.5,
    lon=69.2,
    side_a="Government of Afghanistan",
    side_b="Taliban",
    type_of_violence=1,
    country="Afghanistan",
    best=5,
    date_start="2026-01-15T00:00:00",
    where_description="Kabul Province",
) -> dict:
    """Build a minimal UCDP API result dict."""
    return {
        "id": id_,
        "latitude": lat,
        "longitude": lon,
        "side_a": side_a,
        "side_b": side_b,
        "type_of_violence": type_of_violence,
        "country": country,
        "best": best,
        "high": best + 2,
        "low": best - 2,
        "date_start": date_start,
        "date_end": date_start,
        "where_description": where_description,
        "deaths_a": 2,
        "deaths_b": 3,
        "deaths_civilians": 0,
        "deaths_unknown": 0,
    }


def _make_api_response(results: list[dict], total_pages: int = 1) -> dict:
    """Wrap results in the UCDP API envelope."""
    return {
        "TotalCount": len(results),
        "TotalPages": total_pages,
        "NextPageUrl": None,
        "Result": results,
    }


class TestUcdpFetcherNormalize:
    """Unit tests for _normalize() — no HTTP calls, works directly on raw dicts."""

    def setup_method(self):
        self._fetcher = UcdpFetcher(access_token="test-token")
        self._now = datetime(2026, 3, 27, 12, 0, 0, tzinfo=timezone.utc)

    def test_valid_event_normalizes_correctly(self):
        item = _make_raw_item()
        event = self._fetcher._normalize(item, self._now)

        assert event is not None
        assert event.source_id == "123"
        assert event.source == "ucdp"
        assert event.title == "State-based: Government of Afghanistan vs Taliban"
        assert event.description == "State-based violence in Afghanistan. Estimated fatalities: 5."
        assert event.latitude == 34.5
        assert event.longitude == 69.2
        assert event.place_desc == "Kabul Province"
        assert event.links == []
        assert event.fetched_at == self._now
        assert event.event_date == datetime(2026, 1, 15, 0, 0, 0)

    def test_null_latitude_is_filtered(self):
        item = _make_raw_item(lat=None, lon=69.2)
        event = self._fetcher._normalize(item, self._now)
        assert event is None

    def test_null_longitude_is_filtered(self):
        item = _make_raw_item(lat=34.5, lon=None)
        event = self._fetcher._normalize(item, self._now)
        assert event is None

    def test_zero_zero_coordinates_are_filtered(self):
        item = _make_raw_item(lat=0.0, lon=0.0)
        event = self._fetcher._normalize(item, self._now)
        assert event is None

    def test_nonstate_violence_type(self):
        item = _make_raw_item(type_of_violence=2, side_a="Group A", side_b="Group B")
        event = self._fetcher._normalize(item, self._now)

        assert event is not None
        assert event.title == "Non-state: Group A vs Group B"
        assert "Non-state violence" in event.description

    def test_onesided_violence_type(self):
        item = _make_raw_item(type_of_violence=3, side_a="Militia", side_b="Civilians")
        event = self._fetcher._normalize(item, self._now)

        assert event is not None
        assert event.title == "One-sided: Militia vs Civilians"

    def test_unknown_violence_type(self):
        item = _make_raw_item(type_of_violence=99)
        event = self._fetcher._normalize(item, self._now)

        assert event is not None
        assert event.title.startswith("Unknown:")

    def test_invalid_date_is_none(self):
        item = _make_raw_item(date_start="not-a-date")
        event = self._fetcher._normalize(item, self._now)

        assert event is not None
        assert event.event_date is None

    def test_missing_date_is_none(self):
        item = _make_raw_item()
        item.pop("date_start")
        event = self._fetcher._normalize(item, self._now)

        assert event is not None
        assert event.event_date is None

    def test_empty_where_description_becomes_empty_string(self):
        item = _make_raw_item(where_description=None)
        event = self._fetcher._normalize(item, self._now)

        assert event is not None
        assert event.place_desc == ""

    def test_zero_fatalities_included(self):
        item = _make_raw_item(best=0)
        event = self._fetcher._normalize(item, self._now)

        assert event is not None
        assert "Estimated fatalities: 0" in event.description


class TestUcdpFetcherFetch:
    """Integration-style tests for fetch() — HTTP calls are mocked."""

    def setup_method(self):
        self._fetcher = UcdpFetcher(access_token="test-token")

    def _mock_response(self, data: dict, status_code: int = 200) -> MagicMock:
        mock = MagicMock(spec=httpx.Response)
        mock.status_code = status_code
        mock.json.return_value = data
        # raise_for_status is a no-op for 200, raises for 4xx/5xx
        if status_code >= 400:
            mock.raise_for_status.side_effect = httpx.HTTPStatusError(
                "error", request=MagicMock(), response=mock
            )
        else:
            mock.raise_for_status.return_value = None
        return mock

    def test_single_page_returns_all_events(self):
        items = [_make_raw_item(id_=i, lat=10.0 + i, lon=20.0 + i) for i in range(3)]
        response_data = _make_api_response(items, total_pages=1)

        with patch("httpx.get", return_value=self._mock_response(response_data)):
            events = self._fetcher.fetch()

        assert len(events) == 3

    def test_empty_result_returns_no_events(self):
        response_data = _make_api_response([], total_pages=1)

        with patch("httpx.get", return_value=self._mock_response(response_data)):
            events = self._fetcher.fetch()

        assert events == []

    def test_http_error_returns_partial_results(self):
        # First page succeeds, second page fails — fetch() should return what it got.
        items = [_make_raw_item(id_=1)]
        first_page = _make_api_response(items, total_pages=2)

        call_count = 0

        def fake_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return self._mock_response(first_page)
            raise httpx.HTTPError("Connection failed")

        with patch("httpx.get", side_effect=fake_get):
            events = self._fetcher.fetch()

        # Should have the events from page 1, and the HTTP error on page 2 broke the loop.
        assert len(events) == 1

    def test_events_with_null_coords_filtered_during_fetch(self):
        items = [
            _make_raw_item(id_=1, lat=34.5, lon=69.2),
            _make_raw_item(id_=2, lat=None, lon=None),
            _make_raw_item(id_=3, lat=0.0, lon=0.0),
        ]
        response_data = _make_api_response(items, total_pages=1)

        with patch("httpx.get", return_value=self._mock_response(response_data)):
            events = self._fetcher.fetch()

        assert len(events) == 1
        assert events[0].source_id == "1"

    def test_multipage_fetches_all_pages(self):
        page1_items = [_make_raw_item(id_=1, lat=10.0, lon=20.0)]
        page2_items = [_make_raw_item(id_=2, lat=11.0, lon=21.0)]

        call_count = 0

        def fake_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return self._mock_response(_make_api_response(page1_items, total_pages=2))
            return self._mock_response(_make_api_response(page2_items, total_pages=2))

        with patch("httpx.get", side_effect=fake_get):
            events = self._fetcher.fetch()

        assert call_count == 2
        assert len(events) == 2

    def test_source_name_is_ucdp(self):
        assert self._fetcher.source_name() == "ucdp"

    @pytest.mark.parametrize("status_code", [401, 403, 429, 500, 503])
    def test_http_error_status_codes_handled_gracefully(self, status_code: int):
        with patch("httpx.get") as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                f"HTTP {status_code}",
                request=MagicMock(),
                response=MagicMock(),
            )
            events = self._fetcher.fetch()

        # Should not raise — returns empty list on error.
        assert events == []
