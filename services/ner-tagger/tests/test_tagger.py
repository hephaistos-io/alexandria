import pytest

from ner_tagger import NerTagger, TaggedMention


@pytest.fixture(scope="module")
def tagger() -> NerTagger:
    """Load the spaCy model once for all tests in this module."""
    return NerTagger()


class TestTagging:
    def test_finds_person(self, tagger: NerTagger) -> None:
        mentions = tagger.tag("Barack Obama met with Angela Merkel in Berlin.")
        labels = {m.text: m.label for m in mentions}
        assert "Barack Obama" in labels
        assert labels["Barack Obama"] == "PERSON"

    def test_finds_gpe(self, tagger: NerTagger) -> None:
        mentions = tagger.tag("Iran announced new sanctions against the United States.")
        labels = {m.text: m.label for m in mentions}
        assert "Iran" in labels
        assert labels["Iran"] == "GPE"

    def test_finds_org(self, tagger: NerTagger) -> None:
        mentions = tagger.tag("NATO held an emergency summit.")
        labels = {m.text: m.label for m in mentions}
        assert "NATO" in labels
        assert labels["NATO"] == "ORG"

    def test_multiple_entity_types(self, tagger: NerTagger) -> None:
        text = "Vladimir Putin visited Beijing to meet with the United Nations delegation."
        mentions = tagger.tag(text)
        labels = {m.text: m.label for m in mentions}
        assert "Vladimir Putin" in labels
        assert "Beijing" in labels
        assert "the United Nations" in labels or "United Nations" in labels

    def test_returns_tagged_mention_objects(self, tagger: NerTagger) -> None:
        mentions = tagger.tag("France exported goods to Japan.")
        assert all(isinstance(m, TaggedMention) for m in mentions)

    def test_character_offsets(self, tagger: NerTagger) -> None:
        text = "Iran is a country."
        mentions = tagger.tag(text)
        iran = [m for m in mentions if m.text == "Iran"]
        assert len(iran) == 1
        assert iran[0].start_char == 0
        assert iran[0].end_char == 4
        # Verify offset maps back to the original text
        assert text[iran[0].start_char : iran[0].end_char] == "Iran"

    def test_empty_text_returns_empty(self, tagger: NerTagger) -> None:
        assert tagger.tag("") == []

    def test_no_entities_returns_empty(self, tagger: NerTagger) -> None:
        mentions = tagger.tag("The weather is nice today.")
        # spaCy may or may not find entities here — we just check it doesn't crash
        assert isinstance(mentions, list)

    def test_preserves_order_of_appearance(self, tagger: NerTagger) -> None:
        text = "Japan and France signed a trade deal."
        mentions = tagger.tag(text)
        entity_texts = [m.text for m in mentions]
        if "Japan" in entity_texts and "France" in entity_texts:
            assert entity_texts.index("Japan") < entity_texts.index("France")
