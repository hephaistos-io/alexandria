"""Tests for the GDELT fetcher — parsing, filtering, and title building."""

from datetime import datetime, timezone

from gdelt_fetcher.fetcher import (
    GdeltFetcher,
    _build_title,
    _is_conflict_event,
    _parse_date,
)


class TestIsConflictEvent:
    def test_assault_root_code(self):
        assert _is_conflict_event("18", "180") is True

    def test_fight_root_code(self):
        assert _is_conflict_event("19", "195") is True

    def test_mass_violence_root_code(self):
        assert _is_conflict_event("20", "202") is True

    def test_violent_protest_base_code(self):
        assert _is_conflict_event("14", "145") is True

    def test_peaceful_protest_rejected(self):
        assert _is_conflict_event("14", "141") is False

    def test_diplomatic_event_rejected(self):
        assert _is_conflict_event("04", "040") is False

    def test_coerce_rejected(self):
        """Root code 17 (Coerce) should NOT be included — it's arrests, curfews, etc."""
        assert _is_conflict_event("17", "171") is False


class TestBuildTitle:
    def test_both_actors(self):
        title = _build_title("ISRAEL", "IRAN", "195", "19")
        assert title == "ISRAEL — Aerial weapons — IRAN"

    def test_actor1_only(self):
        title = _build_title("RUSSIA", "", "194", "19")
        assert title == "RUSSIA — Artillery / tank fire"

    def test_actor2_only(self):
        title = _build_title("", "UKRAINE", "193", "19")
        assert title == "Small arms / light weapons — UKRAINE"

    def test_no_actors(self):
        title = _build_title("", "", "183", "18")
        assert title == "Bombing"

    def test_fallback_to_root_code(self):
        """If the base code isn't in the map, fall back to the root code description."""
        title = _build_title("ACTOR", "", "999", "19")
        assert title == "ACTOR — Armed conflict"

    def test_violent_protest(self):
        title = _build_title("", "", "145", "14")
        assert title == "Violent protest"


class TestParseDate:
    def test_valid_date(self):
        result = _parse_date("20260327")
        assert result == datetime(2026, 3, 27, tzinfo=timezone.utc)

    def test_empty_string(self):
        assert _parse_date("") is None

    def test_invalid_date(self):
        assert _parse_date("99999999") is None

    def test_short_string(self):
        assert _parse_date("2026") is None


class TestParseEvents:
    """Test the CSV parsing with a minimal synthetic GDELT row."""

    def _make_row(self, **overrides):
        """Build a 61-column tab-separated GDELT row with sensible defaults."""
        cols = [""] * 61
        cols[0] = overrides.get("event_id", "1234567890")
        cols[1] = overrides.get("sqldate", "20260327")
        cols[6] = overrides.get("actor1", "ISRAEL")
        cols[16] = overrides.get("actor2", "IRAN")
        cols[26] = overrides.get("event_code", "195")
        cols[27] = overrides.get("base_code", "195")
        cols[28] = overrides.get("root_code", "19")
        cols[30] = overrides.get("goldstein", "-9.0")
        cols[31] = overrides.get("num_mentions", "5")
        cols[32] = overrides.get("num_sources", "3")
        cols[52] = overrides.get("place", "Tehran, Iran")
        cols[56] = overrides.get("lat", "35.6892")
        cols[57] = overrides.get("lon", "51.3890")
        cols[60] = overrides.get("source_url", "https://example.com/article")
        return "\t".join(cols)

    def test_conflict_event_parsed(self):
        tsv = self._make_row()
        fetcher = GdeltFetcher()
        now = datetime.now(timezone.utc)
        events = fetcher._parse_events(tsv, now)
        assert len(events) == 1
        e = events[0]
        assert e.source == "gdelt"
        assert e.source_id == "1234567890"
        assert e.latitude == 35.6892
        assert e.longitude == 51.389
        assert e.place_desc == "Tehran, Iran"
        assert "Aerial weapons" in e.title
        assert e.links == ["https://example.com/article"]

    def test_non_conflict_event_filtered(self):
        tsv = self._make_row(root_code="04", base_code="040", event_code="040")
        fetcher = GdeltFetcher()
        events = fetcher._parse_events(tsv, datetime.now(timezone.utc))
        assert len(events) == 0

    def test_zero_coords_filtered(self):
        tsv = self._make_row(lat="0.0", lon="0.0")
        fetcher = GdeltFetcher()
        events = fetcher._parse_events(tsv, datetime.now(timezone.utc))
        assert len(events) == 0

    def test_invalid_lat_filtered(self):
        tsv = self._make_row(lat="", lon="51.3890")
        fetcher = GdeltFetcher()
        events = fetcher._parse_events(tsv, datetime.now(timezone.utc))
        assert len(events) == 0

    def test_multiple_rows(self):
        rows = [
            self._make_row(event_id="111", root_code="19", base_code="195"),
            self._make_row(event_id="222", root_code="04", base_code="040"),  # diplomatic
            self._make_row(event_id="333", root_code="18", base_code="183"),
        ]
        tsv = "\n".join(rows)
        fetcher = GdeltFetcher()
        events = fetcher._parse_events(tsv, datetime.now(timezone.utc))
        assert len(events) == 2
        assert {e.source_id for e in events} == {"111", "333"}
