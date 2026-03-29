"""Tests for auto-naming logic."""

from event_detector.naming import generate_title, slugify


class TestGenerateTitle:
    def test_basic_title(self) -> None:
        title = generate_title(
            entity_qids=["Q801", "Q794"],
            entity_names={"Q801": "Israel", "Q794": "Iran"},
            idf_scores={"Q801": 2.0, "Q794": 1.5},
            article_labels=[["CONFLICT"], ["CONFLICT"], ["POLITICS"]],
        )
        # Q801 has higher IDF, so it comes first.  CONFLICT is dominant label.
        assert title == "Israel-Iran Conflict"

    def test_three_entities(self) -> None:
        title = generate_title(
            entity_qids=["Q801", "Q794", "Q842"],
            entity_names={"Q801": "Israel", "Q794": "Iran", "Q842": "Hezbollah"},
            idf_scores={"Q842": 3.0, "Q801": 2.0, "Q794": 1.5},
            article_labels=[],
        )
        # Q842 (Hezbollah) has highest IDF, comes first.  No labels → no suffix.
        assert title == "Hezbollah-Israel-Iran"

    def test_no_entities_fallback(self) -> None:
        title = generate_title([], {}, {}, [])
        assert title == "Unnamed Event"

    def test_caps_three_entities(self) -> None:
        title = generate_title(
            entity_qids=["Q1", "Q2", "Q3", "Q4"],
            entity_names={"Q1": "A", "Q2": "B", "Q3": "C", "Q4": "D"},
            idf_scores={"Q1": 4.0, "Q2": 3.0, "Q3": 2.0, "Q4": 1.0},
            article_labels=[["POLITICS"]],
        )
        # Only top 3 entities used.
        assert title == "A-B-C Politics"


class TestSlugify:
    def test_basic(self) -> None:
        assert slugify("Israel-Iran-Hezbollah Conflict") == "israel-iran-hezbollah-conflict"

    def test_special_characters(self) -> None:
        assert slugify("U.S.A & Russia: Tensions!") == "u-s-a-russia-tensions"

    def test_collapse_hyphens(self) -> None:
        assert slugify("foo---bar") == "foo-bar"

    def test_strip_leading_trailing(self) -> None:
        assert slugify("--hello--") == "hello"
