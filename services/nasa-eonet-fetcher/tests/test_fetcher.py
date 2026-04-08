from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from nasa_eonet_fetcher.fetcher import NasaEonetFetcher


def _point_geometry(
    lng: float,
    lat: float,
    date: str = "2026-04-01T00:00:00Z",
    magnitude_value: float | None = None,
    magnitude_unit: str | None = None,
) -> dict:
    """Build a GeoJSON Point geometry. Note GeoJSON ordering is [lng, lat].

    EONET puts magnitudeValue/magnitudeUnit on the geometry (not the event),
    so the fixture supports them here.
    """
    geom: dict = {"date": date, "type": "Point", "coordinates": [lng, lat]}
    if magnitude_value is not None:
        geom["magnitudeValue"] = magnitude_value
    if magnitude_unit is not None:
        geom["magnitudeUnit"] = magnitude_unit
    return geom


def _polygon_geometry(
    vertices: list[tuple[float, float]],
    date: str = "2026-04-01T00:00:00Z",
) -> dict:
    """Build a GeoJSON Polygon geometry from (lng, lat) tuples."""
    return {
        "date": date,
        "type": "Polygon",
        "coordinates": [[[v[0], v[1]] for v in vertices]],
    }


# Sentinel used to distinguish "argument not passed" (use default) from
# "argument explicitly passed as empty list" (use the empty list verbatim).
# `categories or [...]` would mistakenly replace an explicit `[]` with the
# default, because empty lists are falsy in Python.
_UNSET = object()


def _make_raw_event(
    id_: str = "EONET_1234",
    title: str = "Wildfire — Northern California",
    description: str = "Active wildfire in the foothills",
    categories=_UNSET,
    sources=_UNSET,
    geometry=_UNSET,
    closed: str | None = None,
) -> dict:
    """Build a minimal EONET API event dict.

    Note: magnitudeValue/magnitudeUnit live on the geometry in EONET v3,
    not on the event itself, so they are passed via `_point_geometry()`.
    """
    if categories is _UNSET:
        categories = [{"id": "wildfires", "title": "Wildfires"}]
    if sources is _UNSET:
        sources = [{"id": "InciWeb", "url": "https://inciweb.example/123"}]
    if geometry is _UNSET:
        geometry = [_point_geometry(-120.5, 38.7)]
    return {
        "id": id_,
        "title": title,
        "description": description,
        "link": f"https://eonet.gsfc.nasa.gov/api/v3/events/{id_}",
        "closed": closed,
        "categories": categories,
        "sources": sources,
        "geometry": geometry,
    }


def _make_api_response(events: list[dict]) -> dict:
    """Wrap a list of events in the EONET response envelope."""
    return {
        "title": "EONET Events",
        "description": "Test fixture",
        "link": "https://eonet.gsfc.nasa.gov/api/v3/events",
        "events": events,
    }


class TestNasaEonetFetcherNormalize:
    """Unit tests for _normalize() — works directly on raw EONET dicts."""

    def setup_method(self):
        self._fetcher = NasaEonetFetcher()
        self._now = datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)

    def test_valid_point_event_normalizes(self):
        item = _make_raw_event()
        event = self._fetcher._normalize(item, self._now)

        assert event is not None
        assert event.source_id == "EONET_1234"
        assert event.source == "nasa_eonet"
        assert event.title == "Wildfire — Northern California"
        assert event.description == "Active wildfire in the foothills"
        assert event.category == "wildfires"
        # GeoJSON [lng, lat] = [-120.5, 38.7] should produce lat=38.7, lng=-120.5
        assert event.latitude == 38.7
        assert event.longitude == -120.5
        assert event.geometry_type == "Point"
        assert event.event_date == datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert event.closed_at is None
        assert event.links == ["https://inciweb.example/123"]
        assert event.fetched_at == self._now

    def test_polygon_centroid_is_mean_of_vertices(self):
        # A simple square: corners at (0,0), (10,0), (10,10), (0,10).
        # Centroid (mean of vertices) is (5, 5).
        # Note: GeoJSON ordering is [lng, lat], so vertices = [(lng, lat), ...]
        polygon = _polygon_geometry([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)])
        item = _make_raw_event(geometry=[polygon])
        event = self._fetcher._normalize(item, self._now)

        assert event is not None
        assert event.geometry_type == "Polygon"
        assert event.latitude == 5.0
        assert event.longitude == 5.0

    def test_latest_geometry_is_picked(self):
        # Three observations of the same wildfire on three days.
        geometries = [
            _point_geometry(-120.0, 38.0, date="2026-04-01T00:00:00Z"),
            _point_geometry(-121.0, 39.0, date="2026-04-03T00:00:00Z"),  # latest
            _point_geometry(-119.5, 37.5, date="2026-04-02T00:00:00Z"),
        ]
        item = _make_raw_event(geometry=geometries)
        event = self._fetcher._normalize(item, self._now)

        assert event is not None
        assert event.latitude == 39.0
        assert event.longitude == -121.0
        assert event.event_date == datetime(2026, 4, 3, 0, 0, 0, tzinfo=timezone.utc)

    def test_closed_event_records_closed_at(self):
        item = _make_raw_event(closed="2026-04-05T18:00:00Z")
        event = self._fetcher._normalize(item, self._now)

        assert event is not None
        assert event.closed_at == datetime(2026, 4, 5, 18, 0, 0, tzinfo=timezone.utc)

    def test_multiple_categories_are_comma_joined(self):
        item = _make_raw_event(
            categories=[
                {"id": "wildfires", "title": "Wildfires"},
                {"id": "severeStorms", "title": "Severe Storms"},
            ]
        )
        event = self._fetcher._normalize(item, self._now)

        assert event is not None
        assert event.category == "wildfires,severeStorms"

    def test_missing_categories_falls_back_to_unknown(self):
        item = _make_raw_event(categories=[])
        event = self._fetcher._normalize(item, self._now)

        assert event is not None
        assert event.category == "unknown"

    def test_event_with_no_geometry_is_skipped(self):
        item = _make_raw_event(geometry=[])
        event = self._fetcher._normalize(item, self._now)
        assert event is None

    def test_event_with_missing_id_is_skipped(self):
        item = _make_raw_event()
        item.pop("id")
        event = self._fetcher._normalize(item, self._now)
        assert event is None

    def test_event_with_missing_title_is_skipped(self):
        item = _make_raw_event()
        item.pop("title")
        event = self._fetcher._normalize(item, self._now)
        assert event is None

    def test_unknown_geometry_type_is_skipped(self):
        # LineString is a valid GeoJSON type but EONET only emits Point/Polygon;
        # if we ever see something else we should skip cleanly rather than crash.
        item = _make_raw_event(
            geometry=[{"date": "2026-04-01T00:00:00Z", "type": "LineString", "coordinates": []}]
        )
        event = self._fetcher._normalize(item, self._now)
        assert event is None

    def test_magnitude_fields_are_read_from_latest_geometry(self):
        # In EONET v3 magnitude lives on the geometry, not the event.
        # The latest observation should be the one whose magnitude wins.
        item = _make_raw_event(
            geometry=[
                _point_geometry(
                    -120.5, 38.7,
                    date="2026-04-01T00:00:00Z",
                    magnitude_value=5000.0,
                    magnitude_unit="acres",
                ),
                _point_geometry(
                    -120.5, 38.7,
                    date="2026-04-03T00:00:00Z",
                    magnitude_value=12500.0,
                    magnitude_unit="acres",
                ),
            ]
        )
        event = self._fetcher._normalize(item, self._now)

        assert event is not None
        assert event.magnitude_value == 12500.0
        assert event.magnitude_unit == "acres"

    def test_missing_magnitude_is_none(self):
        item = _make_raw_event()
        event = self._fetcher._normalize(item, self._now)

        assert event is not None
        assert event.magnitude_value is None
        assert event.magnitude_unit is None

    def test_full_geometry_array_is_preserved(self):
        # The fetcher must hand the full geometry list through to the
        # consumer so it can be stored as JSONB. Earlier versions only
        # kept the latest observation, which threw away the full track.
        geometries = [
            _point_geometry(-120.0, 38.0, date="2026-04-01T00:00:00Z", magnitude_value=40.0, magnitude_unit="kts"),
            _point_geometry(-121.0, 39.0, date="2026-04-02T00:00:00Z", magnitude_value=60.0, magnitude_unit="kts"),
            _point_geometry(-122.0, 40.0, date="2026-04-03T00:00:00Z", magnitude_value=85.0, magnitude_unit="kts"),
        ]
        item = _make_raw_event(geometry=geometries)
        event = self._fetcher._normalize(item, self._now)

        assert event is not None
        assert len(event.geometries) == 3
        # Order is preserved as sent by EONET, not re-sorted.
        assert event.geometries[0]["magnitudeValue"] == 40.0
        assert event.geometries[2]["magnitudeValue"] == 85.0
        # Latest-magnitude scalar matches the last observation.
        assert event.magnitude_value == 85.0

    def test_invalid_geometry_date_falls_to_bottom(self):
        # If the latest-by-date sort encounters an unparseable date, that
        # observation should sort to the bottom and a valid one should win.
        geometries = [
            _point_geometry(-119.0, 37.0, date="2026-04-01T00:00:00Z"),
            {"date": "not-a-date", "type": "Point", "coordinates": [-120.0, 38.0]},
        ]
        item = _make_raw_event(geometry=geometries)
        event = self._fetcher._normalize(item, self._now)

        assert event is not None
        # The valid 2026-04-01 observation should win over the unparseable one.
        assert event.latitude == 37.0
        assert event.longitude == -119.0


class TestNasaEonetFetcherFetch:
    """Integration-style tests for fetch() — HTTP calls are mocked."""

    def setup_method(self):
        self._fetcher = NasaEonetFetcher()

    def _mock_response(self, data: dict, status_code: int = 200) -> MagicMock:
        mock = MagicMock(spec=httpx.Response)
        mock.status_code = status_code
        mock.json.return_value = data
        if status_code >= 400:
            mock.raise_for_status.side_effect = httpx.HTTPStatusError(
                "error", request=MagicMock(), response=mock
            )
        else:
            mock.raise_for_status.return_value = None
        return mock

    def test_returns_all_events(self):
        events_in = [
            _make_raw_event(id_=f"EONET_{i}", geometry=[_point_geometry(-120.0 + i, 38.0 + i)])
            for i in range(3)
        ]
        response_data = _make_api_response(events_in)

        with patch("httpx.get", return_value=self._mock_response(response_data)):
            events = self._fetcher.fetch()

        assert len(events) == 3
        assert {e.source_id for e in events} == {"EONET_0", "EONET_1", "EONET_2"}

    def test_empty_response_returns_no_events(self):
        with patch("httpx.get", return_value=self._mock_response(_make_api_response([]))):
            events = self._fetcher.fetch()
        assert events == []

    def test_events_with_no_geometry_are_filtered(self):
        events_in = [
            _make_raw_event(id_="EONET_OK"),
            _make_raw_event(id_="EONET_NO_GEOM", geometry=[]),
        ]
        with patch(
            "httpx.get",
            return_value=self._mock_response(_make_api_response(events_in)),
        ):
            events = self._fetcher.fetch()

        assert len(events) == 1
        assert events[0].source_id == "EONET_OK"

    def test_source_name_is_nasa_eonet(self):
        assert self._fetcher.source_name() == "nasa_eonet"

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
