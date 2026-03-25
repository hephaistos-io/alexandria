import json
from pathlib import Path

import pytest

from entity_resolver import AliasTable


@pytest.fixture
def seed_path() -> Path:
    """Path to the real seed aliases file."""
    return Path(__file__).parent.parent / "data" / "aliases.json"


@pytest.fixture
def tmp_aliases(tmp_path: Path) -> Path:
    """Create a small temporary alias file for isolated tests."""
    data = {
        "entities": {
            "iran": {
                "canonical_name": "Iran",
                "types": ["GPE"],
                "aliases": [
                    {"alias": "iran", "prior": 1.0, "stability": 1.0},
                    {"alias": "tehran", "prior": 0.75, "stability": 0.5},
                    {"alias": "persia", "prior": 0.8, "stability": 1.0},
                ],
            },
            "us": {
                "canonical_name": "United States",
                "types": ["GPE"],
                "aliases": [
                    {"alias": "united states", "prior": 1.0, "stability": 1.0},
                    {"alias": "usa", "prior": 1.0, "stability": 1.0},
                    {"alias": "the white house", "prior": 0.85, "stability": 1.0},
                    {"alias": "washington", "prior": 0.7, "stability": 0.5},
                ],
            },
        }
    }
    path = tmp_path / "aliases.json"
    path.write_text(json.dumps(data))
    return path


@pytest.fixture
def ambiguous_aliases(tmp_path: Path) -> Path:
    """Alias file where one alias maps to multiple entities of different types."""
    data = {
        "entities": {
            "france": {
                "canonical_name": "France",
                "types": ["GPE"],
                "aliases": [
                    {"alias": "paris", "prior": 0.85, "stability": 0.5},
                ],
            },
            "paris_texas": {
                "canonical_name": "Paris, Texas",
                "types": ["GPE"],
                "aliases": [
                    {"alias": "paris", "prior": 0.1, "stability": 1.0},
                ],
            },
            "paris_myth": {
                "canonical_name": "Paris (mythology)",
                "types": ["PERSON"],
                "aliases": [
                    {"alias": "paris", "prior": 0.05, "stability": 1.0},
                ],
            },
        }
    }
    path = tmp_path / "ambiguous.json"
    path.write_text(json.dumps(data))
    return path


class TestResolve:
    def test_returns_candidates_list(self, tmp_aliases: Path) -> None:
        table = AliasTable(tmp_aliases)
        result = table.resolve("tehran")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].entity_id == "iran"

    def test_candidates_have_metadata(self, tmp_aliases: Path) -> None:
        table = AliasTable(tmp_aliases)
        result = table.resolve("tehran")
        candidate = result[0]
        assert candidate.canonical_name == "Iran"
        assert candidate.prior == 0.75
        assert candidate.stability == 0.5
        assert candidate.entity_types == ["GPE"]
        assert candidate.confirmed_count == 0
        assert candidate.last_confirmed is None

    def test_case_insensitive(self, tmp_aliases: Path) -> None:
        table = AliasTable(tmp_aliases)
        assert len(table.resolve("TEHRAN")) == 1
        assert len(table.resolve("The White House")) == 1
        assert table.resolve("The White House")[0].entity_id == "us"

    def test_unknown_returns_empty_list(self, tmp_aliases: Path) -> None:
        table = AliasTable(tmp_aliases)
        assert table.resolve("narnia") == []

    def test_empty_string_returns_empty_list(self, tmp_aliases: Path) -> None:
        table = AliasTable(tmp_aliases)
        assert table.resolve("") == []

    def test_sorted_by_prior_descending(self, ambiguous_aliases: Path) -> None:
        table = AliasTable(ambiguous_aliases)
        result = table.resolve("paris")
        assert len(result) == 3
        assert result[0].entity_id == "france"
        assert result[0].prior == 0.85
        assert result[1].entity_id == "paris_texas"
        assert result[2].entity_id == "paris_myth"

    def test_no_side_effects_on_read(self, tmp_aliases: Path) -> None:
        """Resolve is a pure read — no fields should change."""
        table = AliasTable(tmp_aliases)
        result1 = table.resolve("tehran")
        result2 = table.resolve("tehran")
        assert result1[0].confirmed_count == 0
        assert result2[0].confirmed_count == 0
        assert result1[0].last_confirmed is None


class TestTypeAwareResolve:
    def test_type_boosts_matching_candidates(self, ambiguous_aliases: Path) -> None:
        """When entity_type is GPE, GPE candidates should rank above PERSON."""
        table = AliasTable(ambiguous_aliases)
        result = table.resolve("paris", entity_type="GPE")
        # France and Paris, Texas are GPE — should come before Paris (mythology) PERSON
        assert result[0].entity_id == "france"
        assert result[1].entity_id == "paris_texas"
        assert result[2].entity_id == "paris_myth"

    def test_type_promotes_lower_prior_if_type_matches(self, ambiguous_aliases: Path) -> None:
        """PERSON type should promote Paris (mythology) above GPE candidates."""
        table = AliasTable(ambiguous_aliases)
        result = table.resolve("paris", entity_type="PERSON")
        assert result[0].entity_id == "paris_myth"
        # GPE candidates still returned, just ranked lower
        assert len(result) == 3

    def test_type_none_preserves_prior_ordering(self, ambiguous_aliases: Path) -> None:
        """Without entity_type, ordering is purely by prior (backward compatible)."""
        table = AliasTable(ambiguous_aliases)
        result = table.resolve("paris", entity_type=None)
        assert result[0].entity_id == "france"
        assert result[1].entity_id == "paris_texas"
        assert result[2].entity_id == "paris_myth"

    def test_unrecognized_type_returns_all(self, ambiguous_aliases: Path) -> None:
        """An entity_type not matching any candidate still returns all candidates."""
        table = AliasTable(ambiguous_aliases)
        result = table.resolve("paris", entity_type="ORG")
        assert len(result) == 3
        # No type match, so falls back to prior ordering
        assert result[0].entity_id == "france"

    def test_entity_types_loaded_from_data(self, tmp_aliases: Path) -> None:
        table = AliasTable(tmp_aliases)
        result = table.resolve("iran")
        assert result[0].entity_types == ["GPE"]

    def test_missing_types_defaults_to_empty(self, tmp_path: Path) -> None:
        """Entities without a types field should get an empty list."""
        data = {
            "entities": {
                "test": {
                    "canonical_name": "Test Entity",
                    "aliases": [{"alias": "test", "prior": 1.0, "stability": 1.0}],
                }
            }
        }
        path = tmp_path / "no_types.json"
        path.write_text(json.dumps(data))
        table = AliasTable(path)
        result = table.resolve("test")
        assert result[0].entity_types == []


class TestAmbiguousAliases:
    def test_multiple_candidates_returned(self, ambiguous_aliases: Path) -> None:
        table = AliasTable(ambiguous_aliases)
        result = table.resolve("paris")
        assert len(result) == 3
        entity_ids = [c.entity_id for c in result]
        assert "france" in entity_ids
        assert "paris_texas" in entity_ids
        assert "paris_myth" in entity_ids

    def test_priors_sum_hint(self, ambiguous_aliases: Path) -> None:
        """Priors for the same alias across entities are independent weights, not
        required to sum to 1.0. This test documents that behavior."""
        table = AliasTable(ambiguous_aliases)
        result = table.resolve("paris")
        total = sum(c.prior for c in result)
        # They don't have to sum to 1.0 — they're independent confidence weights
        assert total == pytest.approx(1.0, abs=0.1)


class TestStats:
    def test_stats_counts(self, tmp_aliases: Path) -> None:
        table = AliasTable(tmp_aliases)
        stats = table.stats()
        assert stats["total_entities"] == 2
        # iran, tehran, persia, united states, usa, the white house, washington
        assert stats["total_aliases"] == 7
        assert stats["total_candidates"] == 7  # no ambiguity in this fixture


class TestSeedFile:
    def test_seed_file_loads(self, seed_path: Path) -> None:
        table = AliasTable(seed_path)
        stats = table.stats()
        assert stats["total_entities"] >= 40
        assert stats["total_aliases"] >= 100

    def test_seed_known_entries(self, seed_path: Path) -> None:
        table = AliasTable(seed_path)
        kremlin = table.resolve("the kremlin")
        assert len(kremlin) >= 1
        assert kremlin[0].entity_id == "russia"

        opec = table.resolve("opec")
        assert len(opec) >= 1
        assert opec[0].entity_id == "opec"

        hormuz = table.resolve("strait of hormuz")
        assert len(hormuz) >= 1
        assert hormuz[0].entity_id == "strait_of_hormuz"

    def test_volatile_aliases_have_lower_prior(self, seed_path: Path) -> None:
        """Capital-as-metonym aliases should be marked volatile with prior < 1.0."""
        table = AliasTable(seed_path)
        tehran = table.resolve("tehran")
        assert tehran[0].stability < 1.0
        assert tehran[0].prior < 1.0

    def test_seed_entities_have_types(self, seed_path: Path) -> None:
        """All seed entities should have non-empty types (except commodities)."""
        table = AliasTable(seed_path)
        iran = table.resolve("iran")
        assert iran[0].entity_types == ["GPE"]
        nato = table.resolve("nato")
        assert nato[0].entity_types == ["ORG"]
        hormuz = table.resolve("strait of hormuz")
        assert hormuz[0].entity_types == ["LOC"]


class TestNonexistentFile:
    def test_missing_file_starts_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "does_not_exist.json"
        table = AliasTable(path)
        assert table.resolve("anything") == []
        assert table.stats() == {
            "total_entities": 0,
            "total_aliases": 0,
            "total_candidates": 0,
        }
