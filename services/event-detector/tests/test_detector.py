"""Tests for the core detection/clustering logic."""

import math
from datetime import datetime, timezone

from event_detector.detector import (
    _haversine_km,
    cluster_articles,
    compute_entity_idf,
    compute_heat,
    determine_status,
    match_conflicts,
    match_existing_event,
)
from event_detector.models import ArticleRow, ConflictRow, ExistingEvent


def _article(
    id_: int,
    qids: list[str],
    labels: list[str] | None = None,
    published_at: datetime | None = None,
) -> ArticleRow:
    """Helper to build a minimal ArticleRow for testing."""
    entities = [{"wikidata_id": qid, "text": qid, "canonical_name": qid} for qid in qids]
    return ArticleRow(
        id=id_,
        title=f"Article {id_}",
        entities=entities,
        automatic_labels=labels,
        published_at=published_at,
    )


class TestComputeEntityIdf:
    def test_empty_articles(self) -> None:
        assert compute_entity_idf([]) == {}

    def test_single_article(self) -> None:
        articles = [_article(1, ["Q1", "Q2"])]
        idf = compute_entity_idf(articles)
        # log(1/1) = 0 for both entities (they appear in 100% of articles).
        assert idf["Q1"] == 0.0
        assert idf["Q2"] == 0.0

    def test_distinctive_entity_has_higher_idf(self) -> None:
        articles = [
            _article(1, ["Q1", "Q2"]),
            _article(2, ["Q1", "Q3"]),
            _article(3, ["Q1", "Q4"]),
        ]
        idf = compute_entity_idf(articles)
        # Q1 appears in all 3 → IDF = log(3/3) = 0
        assert idf["Q1"] == 0.0
        # Q2 appears in 1 of 3 → IDF = log(3/1) ≈ 1.099
        assert abs(idf["Q2"] - math.log(3)) < 0.001


class TestClusterArticles:
    def test_two_articles_shared_entities_form_cluster(self) -> None:
        """Articles sharing 2+ distinctive entities should cluster together."""
        # Background articles ensure Q801/Q794 don't appear in 100% of articles
        # (which would give them IDF = 0 and fail the IDF threshold).
        articles = [
            _article(1, ["Q801", "Q794", "Q100"]),  # Israel, Iran, + unique
            _article(2, ["Q801", "Q794", "Q200"]),
            _article(3, ["Q801", "Q794", "Q300"]),
            # Background — unrelated articles to give Q801/Q794 high enough IDF.
            # With 10 total articles, Q801/Q794 appear in 3/10 → IDF ≈ 1.2 each,
            # sum ≈ 2.4 which clears the MIN_IDF_SUM = 2.0 threshold.
            _article(10, ["Q900", "Q901"]),
            _article(11, ["Q902", "Q903"]),
            _article(12, ["Q904", "Q905"]),
            _article(13, ["Q906", "Q907"]),
            _article(14, ["Q908", "Q909"]),
            _article(15, ["Q910", "Q911"]),
            _article(16, ["Q912", "Q913"]),
        ]
        idf = compute_entity_idf(articles)
        clusters = cluster_articles(articles, idf)
        assert len(clusters) == 1
        assert len(clusters[0]) == 3

    def test_common_entity_only_no_cluster(self) -> None:
        """Articles sharing only a very common entity should NOT cluster."""
        # Q30 (common) appears in all articles.  Each pair also shares Q30,
        # but Q30's IDF is 0 so the IDF sum won't meet the threshold.
        articles = [
            _article(1, ["Q30", "Q100"]),
            _article(2, ["Q30", "Q200"]),
            _article(3, ["Q30", "Q300"]),
        ]
        idf = compute_entity_idf(articles)
        clusters = cluster_articles(articles, idf)
        assert len(clusters) == 0

    def test_small_cluster_filtered_out(self) -> None:
        """Clusters with fewer than 3 articles are dropped."""
        articles = [
            _article(1, ["Q801", "Q794"]),
            _article(2, ["Q801", "Q794"]),
        ]
        idf = compute_entity_idf(articles)
        clusters = cluster_articles(articles, idf)
        assert len(clusters) == 0

    def test_two_separate_clusters(self) -> None:
        """Articles with different entity groups form separate clusters."""
        articles = [
            # Cluster A: Q1, Q2
            _article(1, ["Q1", "Q2", "Q100"]),
            _article(2, ["Q1", "Q2", "Q200"]),
            _article(3, ["Q1", "Q2", "Q300"]),
            # Cluster B: Q3, Q4
            _article(4, ["Q3", "Q4", "Q400"]),
            _article(5, ["Q3", "Q4", "Q500"]),
            _article(6, ["Q3", "Q4", "Q600"]),
            # Background articles for IDF.
            _article(10, ["Q900", "Q901"]),
            _article(11, ["Q902", "Q903"]),
            _article(12, ["Q904", "Q905"]),
        ]
        idf = compute_entity_idf(articles)
        clusters = cluster_articles(articles, idf)
        assert len(clusters) == 2

    def test_no_resolved_entities_skipped(self) -> None:
        """Articles with no wikidata_id entities produce no clusters."""
        articles = [
            ArticleRow(1, "A", [{"text": "foo"}], None, None),
            ArticleRow(2, "B", [{"text": "bar"}], None, None),
            ArticleRow(3, "C", [{"text": "baz"}], None, None),
        ]
        idf = compute_entity_idf(articles)
        clusters = cluster_articles(articles, idf)
        assert len(clusters) == 0


class TestComputeHeat:
    def test_basic_heat(self) -> None:
        heat = compute_heat(article_count=9, conflict_count=0, hours_since_last=0.0)
        # 9^0.5 * max(1, 0) * exp(0) = 3.0
        assert abs(heat - 3.0) < 0.001

    def test_heat_with_conflicts(self) -> None:
        heat = compute_heat(article_count=4, conflict_count=8, hours_since_last=0.0)
        # 4^0.5 * 8^0.3 * 1 = 2 * ~1.866 = ~3.732
        expected = (4**0.5) * (8**0.3)
        assert abs(heat - expected) < 0.001

    def test_heat_decays_over_time(self) -> None:
        heat_now = compute_heat(10, 5, hours_since_last=0.0)
        heat_later = compute_heat(10, 5, hours_since_last=72.0)
        assert heat_later < heat_now

    def test_heat_halves_in_about_69_hours(self) -> None:
        heat_0 = compute_heat(10, 0, 0.0)
        half_life = math.log(2) / 0.01  # ≈ 69.3 hours
        heat_half = compute_heat(10, 0, half_life)
        assert abs(heat_half - heat_0 / 2) < 0.01


class TestDetermineStatus:
    def test_high_heat_is_active(self) -> None:
        assert determine_status(6.0) == "active"

    def test_low_heat_is_historical(self) -> None:
        assert determine_status(0.3) == "historical"

    def test_moderate_heat_new_is_emerging(self) -> None:
        assert determine_status(3.0) == "emerging"

    def test_active_drops_to_cooling(self) -> None:
        assert determine_status(1.5, current_status="active") == "cooling"

    def test_cooling_stays_cooling(self) -> None:
        assert determine_status(1.5, current_status="cooling") == "cooling"

    def test_historical_can_reemerge(self) -> None:
        assert determine_status(6.0, current_status="historical") == "active"

    def test_any_state_to_historical(self) -> None:
        assert determine_status(0.1, current_status="active") == "historical"
        assert determine_status(0.1, current_status="emerging") == "historical"
        assert determine_status(0.1, current_status="cooling") == "historical"


class TestMatchConflicts:
    def test_nearby_conflict_matched(self) -> None:
        conflicts = [ConflictRow(id=1, latitude=31.5, longitude=34.5, event_date=None)]
        # Tel Aviv is roughly 31.77, 35.21 — within 100km.
        matched = match_conflicts(31.77, 35.21, conflicts, max_distance_km=150.0)
        assert matched == [1]

    def test_distant_conflict_excluded(self) -> None:
        conflicts = [ConflictRow(id=1, latitude=55.0, longitude=37.0, event_date=None)]
        # Moscow (55, 37) is far from Tel Aviv (31.77, 35.21).
        matched = match_conflicts(31.77, 35.21, conflicts, max_distance_km=100.0)
        assert matched == []

    def test_no_centroid_returns_empty(self) -> None:
        conflicts = [ConflictRow(id=1, latitude=31.0, longitude=34.0, event_date=None)]
        assert match_conflicts(None, None, conflicts) == []


class TestMatchExistingEvent:
    def test_good_overlap_matches(self) -> None:
        existing = [
            ExistingEvent(
                id=1,
                slug="test",
                title="Test",
                status="active",
                heat=5.0,
                entity_qids=["Q1", "Q2", "Q3"],
                centroid_lat=None,
                centroid_lng=None,
                first_seen=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
            ),
        ]
        # Cluster shares Q1, Q2 — Jaccard = 2/4 = 0.5 (above 0.3 threshold).
        result = match_existing_event({"Q1", "Q2", "Q4"}, existing)
        assert result is not None
        assert result.id == 1

    def test_low_overlap_no_match(self) -> None:
        existing = [
            ExistingEvent(
                id=1,
                slug="test",
                title="Test",
                status="active",
                heat=5.0,
                entity_qids=["Q1", "Q2", "Q3", "Q4", "Q5"],
                centroid_lat=None,
                centroid_lng=None,
                first_seen=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
            ),
        ]
        # Cluster shares only Q1 — Jaccard = 1/7 ≈ 0.14 (below 0.3).
        result = match_existing_event({"Q1", "Q10", "Q11"}, existing)
        assert result is None

    def test_empty_existing_returns_none(self) -> None:
        assert match_existing_event({"Q1"}, []) is None


class TestHaversine:
    def test_same_point_is_zero(self) -> None:
        assert _haversine_km(31.0, 34.0, 31.0, 34.0) == 0.0

    def test_known_distance(self) -> None:
        # London (51.5, -0.12) to Paris (48.86, 2.35) ≈ 344 km.
        dist = _haversine_km(51.5, -0.12, 48.86, 2.35)
        assert 340 < dist < 350
