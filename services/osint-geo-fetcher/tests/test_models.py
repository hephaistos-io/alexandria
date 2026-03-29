from datetime import datetime, timezone

from osint_geo_fetcher.models import ConflictEvent


def test_conflict_event_creation():
    event = ConflictEvent(
        source_id="123",
        source="bellingcat",
        title="Test Event",
        description="A test conflict event",
        latitude=48.85,
        longitude=2.35,
        event_date=datetime(2026, 3, 20, tzinfo=timezone.utc),
        country="France",
        place_desc="Paris, France",
        links=["https://example.com"],
        fetched_at=datetime.now(timezone.utc),
    )
    assert event.source == "bellingcat"
    assert event.latitude == 48.85
