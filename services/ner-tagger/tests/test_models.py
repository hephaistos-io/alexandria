from ner_tagger.models import TaggedArticle, TaggedMention


class TestTaggedMention:
    def test_creation(self) -> None:
        m = TaggedMention(text="Iran", label="GPE", start_char=0, end_char=4)
        assert m.text == "Iran"
        assert m.label == "GPE"
        assert m.start_char == 0
        assert m.end_char == 4


class TestTaggedArticle:
    def test_creation(self) -> None:
        article = TaggedArticle(
            source="rss",
            origin="bbc_world",
            title="Test Article",
            url="https://example.com/test",
            summary="A summary.",
            published="2026-03-20T14:00:00+00:00",
            fetched_at="2026-03-20T14:30:00+00:00",
            content="Iran announced new sanctions.",
            scraped_at="2026-03-20T14:31:00+00:00",
            entities=[{"text": "Iran", "label": "GPE", "start": 0, "end": 4}],
            tagged_at="2026-03-20T14:32:00+00:00",
        )
        assert article.title == "Test Article"
        assert len(article.entities) == 1
        assert article.entities[0]["label"] == "GPE"

    def test_published_can_be_none(self) -> None:
        article = TaggedArticle(
            source="rss",
            origin="bbc_world",
            title="Test",
            url="https://example.com",
            summary="Summary",
            published=None,
            fetched_at="2026-03-20T14:30:00+00:00",
            content="Some content.",
            scraped_at="2026-03-20T14:31:00+00:00",
            entities=[],
            tagged_at="2026-03-20T14:32:00+00:00",
        )
        assert article.published is None

    def test_empty_entities(self) -> None:
        article = TaggedArticle(
            source="rss",
            origin="bbc_world",
            title="Test",
            url="https://example.com",
            summary="Summary",
            published=None,
            fetched_at="2026-03-20T14:30:00+00:00",
            content="The weather is nice today.",
            scraped_at="2026-03-20T14:31:00+00:00",
            entities=[],
            tagged_at="2026-03-20T14:32:00+00:00",
        )
        assert article.entities == []

    def test_multiple_entities(self) -> None:
        entities = [
            {"text": "Iran", "label": "GPE", "start": 0, "end": 4},
            {"text": "$6 million", "label": "MONEY", "start": 14, "end": 24},
            {"text": "Norway", "label": "GPE", "start": 53, "end": 59},
        ]
        article = TaggedArticle(
            source="rss",
            origin="bbc_world",
            title="Test",
            url="https://example.com",
            summary="Summary",
            published="2026-03-20T14:00:00+00:00",
            fetched_at="2026-03-20T14:30:00+00:00",
            content="Iran received $6 million in humanitarian aid from Norway.",
            scraped_at="2026-03-20T14:31:00+00:00",
            entities=entities,
            tagged_at="2026-03-20T14:32:00+00:00",
        )
        assert len(article.entities) == 3
        labels = {e["label"] for e in article.entities}
        assert "GPE" in labels
        assert "MONEY" in labels
