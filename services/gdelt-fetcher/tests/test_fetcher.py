"""Tests for the GDELT fetcher — parsing, filtering, and title building."""

from datetime import datetime, timezone

from gdelt_fetcher.fetcher import (
    GdeltFetcher,
    _build_title,
    _haversine_km,
    _is_conflict_event,
    _parse_coord,
    _parse_date,
    _resolve_geo,
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


class TestParseCoord:
    def test_happy_path(self):
        assert _parse_coord("35.6892", "51.3890") == (35.6892, 51.389)

    def test_zero_zero_sentinel_rejected(self):
        """GDELT uses (0, 0) as 'unknown location' — treat as missing."""
        assert _parse_coord("0", "0") is None
        assert _parse_coord("0.0", "0.0") is None

    def test_zero_lat_nonzero_lng_accepted(self):
        """A point on the equator that isn't (0,0) is a real location."""
        assert _parse_coord("0.0", "5.0") == (0.0, 5.0)

    def test_nonzero_lat_zero_lng_accepted(self):
        """A point on the prime meridian (e.g., London at ~0 lng) is valid."""
        assert _parse_coord("51.5", "0") == (51.5, 0.0)

    def test_empty_lat(self):
        assert _parse_coord("", "51.389") is None

    def test_empty_lng(self):
        assert _parse_coord("35.6892", "") is None

    def test_both_empty(self):
        assert _parse_coord("", "") is None

    def test_malformed_float(self):
        assert _parse_coord("not-a-number", "51.389") is None

    def test_whitespace_stripped(self):
        """Raw row values may carry whitespace; _parse_coord should handle it."""
        assert _parse_coord(" 35.6892 ", " 51.3890 ") == (35.6892, 51.389)

    def test_whitespace_only_treated_as_empty(self):
        assert _parse_coord("   ", "51.389") is None


class TestHaversineKm:
    def test_same_point(self):
        assert _haversine_km((0.0, 0.0), (0.0, 0.0)) == 0.0

    def test_tehran_jerusalem(self):
        # Ground truth ≈ 1590 km. Haversine gives ~1 km error over this range.
        d = _haversine_km((35.6892, 51.3890), (31.7683, 35.2137))
        assert 1550 < d < 1650

    def test_tehran_geneva(self):
        # Ground truth ≈ 3900 km — comfortably beyond the 2000 km threshold.
        d = _haversine_km((35.6892, 51.3890), (46.1956, 6.14811))
        assert 3800 < d < 4000

    def test_antimeridian_wraparound(self):
        """Two points straddling the ±180° meridian must compute the short path.

        (0, 179) and (0, -179) are ~222 km apart going east, not ~40000 km
        going the long way round. A naive flat-earth diff on raw longitudes
        would give the wrong answer; haversine's sin(dlambda/2) term handles
        this correctly because sin(178°/2) == sin(-178°/2 + 180°). This test
        pins the behavior so a future "simplification" can't silently break
        Aleutian / Kamchatka events.
        """
        d = _haversine_km((0.0, 179.0), (0.0, -179.0))
        assert 200 < d < 250


class TestResolveGeo:
    TEHRAN = (35.6892, 51.3890)
    TEL_AVIV = (32.0667, 34.7667)
    GENEVA = (46.1956, 6.14811)
    NEW_YORK = (40.7128, -74.0060)
    # Default root code for armed conflict — Actor2Geo is preferred for these.
    CONFLICT_ROOT = "19"
    PROTEST_ROOT = "14"

    def test_prefers_actor2_for_armed_conflict(self):
        result = _resolve_geo(
            actor1=self.TEHRAN, actor2=self.TEL_AVIV, action=self.GENEVA,
            actor1_place="Tehran", actor2_place="Tel Aviv", action_place="Geneva",
            root_code=self.CONFLICT_ROOT,
        )
        assert result is not None
        coord, place = result
        assert coord == self.TEL_AVIV
        assert place == "Tel Aviv"

    def test_falls_back_to_actor1_when_actor2_missing(self):
        result = _resolve_geo(
            actor1=self.TEHRAN, actor2=None, action=self.TEHRAN,
            actor1_place="Tehran", actor2_place="", action_place="Tehran",
            root_code=self.CONFLICT_ROOT,
        )
        assert result is not None
        assert result[0] == self.TEHRAN

    def test_single_signal_trusted(self):
        """Only ActionGeo populated — we have nothing to validate against."""
        result = _resolve_geo(
            actor1=None, actor2=None, action=self.GENEVA,
            actor1_place="", actor2_place="", action_place="Geneva",
            root_code=self.CONFLICT_ROOT,
        )
        assert result is not None
        assert result[0] == self.GENEVA

    def test_dropped_when_two_signals_disagree(self):
        """Tel Aviv is too far from New York (only other signal) → drop."""
        result = _resolve_geo(
            actor1=None, actor2=self.TEL_AVIV, action=self.NEW_YORK,
            actor1_place="", actor2_place="Tel Aviv", action_place="New York",
            root_code=self.CONFLICT_ROOT,
        )
        assert result is None

    def test_kept_when_any_signal_agrees(self):
        """Tel Aviv agrees with Tehran (within 2000 km) even though Geneva doesn't."""
        result = _resolve_geo(
            actor1=self.TEHRAN, actor2=self.TEL_AVIV, action=self.GENEVA,
            actor1_place="Tehran", actor2_place="Tel Aviv", action_place="Geneva",
            root_code=self.CONFLICT_ROOT,
        )
        assert result is not None
        assert result[0] == self.TEL_AVIV

    def test_no_geo_returns_none(self):
        result = _resolve_geo(
            actor1=None, actor2=None, action=None,
            actor1_place="", actor2_place="", action_place="",
            root_code=self.CONFLICT_ROOT,
        )
        assert result is None

    def test_falls_through_polluted_top_candidate(self):
        """Actor2Geo is polluted (Geneva) but Actor1+Action agree (Tehran↔Tel Aviv).

        The resolver must not commit to the top-priority candidate and give
        up. It walks the list in order: Geneva fails (too far from both
        Tehran and Tel Aviv), Tehran passes (agrees with Tel Aviv), and the
        event is kept with Tehran's coordinates. This protects legitimate
        events from being dropped when the target-preferred column is the
        one that got polluted.
        """
        result = _resolve_geo(
            actor1=self.TEHRAN,
            actor2=self.GENEVA,  # the polluted one
            action=self.TEL_AVIV,
            actor1_place="Tehran",
            actor2_place="Geneva",
            action_place="Tel Aviv",
            root_code=self.CONFLICT_ROOT,
        )
        assert result is not None
        assert result[0] == self.TEHRAN
        assert result[1] == "Tehran"

    def test_protest_skips_actor2_preference(self):
        """For violent protest (root 14), Actor2 is usually an abstract entity
        ("GOVERNMENT") geocoded to the capital. We should prefer Actor1Geo
        (the protesters' location) instead.
        """
        # Protest is in Istanbul; Actor2Geo points to Ankara (capital) where
        # the abstract "GOVERNMENT" entity lives. With Actor2Geo preferred
        # we'd snap to Ankara — wrong. With the protest-aware preference
        # chain we should stay in Istanbul.
        istanbul = (41.0082, 28.9784)
        ankara = (39.9334, 32.8597)
        result = _resolve_geo(
            actor1=istanbul,
            actor2=ankara,
            action=istanbul,
            actor1_place="Istanbul",
            actor2_place="Ankara",
            action_place="Istanbul",
            root_code=self.PROTEST_ROOT,
        )
        assert result is not None
        assert result[0] == istanbul
        assert result[1] == "Istanbul"


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
        cols[36] = overrides.get("actor1_geo_place", "")
        cols[40] = overrides.get("actor1_geo_lat", "")
        cols[41] = overrides.get("actor1_geo_lon", "")
        cols[44] = overrides.get("actor2_geo_place", "")
        cols[48] = overrides.get("actor2_geo_lat", "")
        cols[49] = overrides.get("actor2_geo_lon", "")
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

    def test_geneva_dateline_leak_rerouted(self):
        """Tehran-Israel event whose ActionGeo points to Geneva should snap to Tel Aviv.

        This is the exact bug that motivated the filter: GDELT's article-text
        geocoder puts the action in whatever city the wire story was filed
        from. With Actor1Geo = Tehran and Actor2Geo = Tel Aviv populated,
        the resolver should pick Actor2Geo (target of the attack) and
        validate it against Actor1Geo (1600 km away, within threshold).
        """
        tsv = self._make_row(
            actor1_geo_lat="35.6892", actor1_geo_lon="51.3890",  # Tehran
            actor1_geo_place="Tehran, Iran",
            actor2_geo_lat="32.0667", actor2_geo_lon="34.7667",  # Tel Aviv
            actor2_geo_place="Tel Aviv, Israel",
            lat="46.1956", lon="6.14811",  # Geneva — the dateline leak
            place="Geneva, Switzerland",
        )
        fetcher = GdeltFetcher()
        events = fetcher._parse_events(tsv, datetime.now(timezone.utc))
        assert len(events) == 1
        # Coords should be Tel Aviv (Actor2Geo), not Geneva (ActionGeo).
        assert events[0].latitude == 32.0667
        assert events[0].longitude == 34.7667
        assert events[0].place_desc == "Tel Aviv, Israel"

    def test_two_signal_disagreement_dropped(self):
        """Two populated geo columns that disagree by more than the threshold
        should drop the row. Jerusalem ↔ New York ≈ 9000 km, outside the
        2000 km threshold, and there's no third signal to rescue it → drop.
        """
        tsv = self._make_row(
            actor2_geo_lat="31.7683", actor2_geo_lon="35.2137",  # Jerusalem
            actor2_geo_place="Jerusalem, Israel",
            lat="40.7128", lon="-74.0060",  # New York
            place="New York, United States",
        )
        fetcher = GdeltFetcher()
        events = fetcher._parse_events(tsv, datetime.now(timezone.utc))
        assert len(events) == 0

    def test_lone_action_geo_trusted(self):
        """If only ActionGeo is populated, we trust it — nothing to validate against."""
        tsv = self._make_row()  # default row has only ActionGeo set
        fetcher = GdeltFetcher()
        events = fetcher._parse_events(tsv, datetime.now(timezone.utc))
        assert len(events) == 1
        assert events[0].latitude == 35.6892

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
