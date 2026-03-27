from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from osint_geo_fetcher.fetcher import OsintGeoFetcher


def _make_event(id_="1", lat=48.85, lon=2.35, title="Test"):
    """Create a mock osint-geo-extractor Event."""
    event = MagicMock()
    event.id = id_
    event.latitude = lat
    event.longitude = lon
    event.title = title
    event.description = "desc"
    event.date = datetime(2026, 1, 1, tzinfo=timezone.utc)
    event.place_desc = "Place"
    event.links = ["https://example.com"]
    event.source = "test"
    return event


class TestOsintGeoFetcher:
    def test_filters_null_coordinates(self):
        fetcher = OsintGeoFetcher()
        with patch.dict("osint_geo_fetcher.fetcher.SOURCES", {
            "test": lambda: [_make_event(lat=None, lon=None)],
        }, clear=True):
            events = fetcher.fetch()
            assert len(events) == 0

    def test_filters_zero_coordinates(self):
        fetcher = OsintGeoFetcher()
        with patch.dict("osint_geo_fetcher.fetcher.SOURCES", {
            "test": lambda: [_make_event(lat=0.0, lon=0.0)],
        }, clear=True):
            events = fetcher.fetch()
            assert len(events) == 0

    def test_normalizes_valid_event(self):
        fetcher = OsintGeoFetcher()
        with patch.dict("osint_geo_fetcher.fetcher.SOURCES", {
            "bellingcat": lambda: [_make_event()],
        }, clear=True):
            events = fetcher.fetch()
            assert len(events) == 1
            assert events[0].source == "bellingcat"
            assert events[0].latitude == 48.85

    def test_source_failure_doesnt_crash(self):
        fetcher = OsintGeoFetcher()
        with patch.dict("osint_geo_fetcher.fetcher.SOURCES", {
            "broken": lambda: (_ for _ in ()).throw(RuntimeError("API down")),
            "working": lambda: [_make_event()],
        }, clear=True):
            events = fetcher.fetch()
            assert len(events) == 1
