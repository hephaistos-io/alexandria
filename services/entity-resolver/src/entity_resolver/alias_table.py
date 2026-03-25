import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Candidate:
    """A possible entity match for an alias, with metadata."""

    entity_id: str
    canonical_name: str
    prior: float  # 0.0–1.0, how often this alias historically refers to this entity
    stability: float  # 0.0–1.0, how stable this mapping is over time (1.0 = permanent)
    entity_types: list[str] = field(default_factory=list)  # compatible spaCy NER labels
    confirmed_count: int = 0  # times this mapping was confirmed correct by downstream
    last_confirmed: str | None = None  # ISO timestamp of last confirmed resolution


class AliasTable:
    """Stage 1 of the entity resolution pipeline: fast O(1) candidate lookup.

    Read-only alias table. Loads aliases from a JSON file and resolves
    text mentions to candidate entities. Does not mutate state — mutations
    are handled by a separate feedback service.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        # lowercase alias → list of Candidate
        self._lookup: dict[str, list[Candidate]] = {}
        self._entity_count = 0

        if path.exists():
            self._load()

    def _load(self) -> None:
        with open(self._path) as f:
            data = json.load(f)

        entities = data.get("entities", {})
        self._entity_count = len(entities)

        for entity_id, entity_data in entities.items():
            canonical = entity_data["canonical_name"]
            entity_types = entity_data.get("types", [])

            for alias_entry in entity_data.get("aliases", []):
                alias_lower = alias_entry["alias"].lower()
                candidate = Candidate(
                    entity_id=entity_id,
                    canonical_name=canonical,
                    prior=alias_entry.get("prior", 1.0),
                    stability=alias_entry.get("stability", 1.0),
                    entity_types=entity_types,
                    confirmed_count=alias_entry.get("confirmed_count", 0),
                    last_confirmed=alias_entry.get("last_confirmed"),
                )
                self._lookup.setdefault(alias_lower, []).append(candidate)

    def resolve(self, mention: str, entity_type: str | None = None) -> list[Candidate]:
        """Look up a mention and return candidate entities.

        When entity_type is provided (e.g. "GPE" from spaCy NER), candidates
        whose entity_types include the given type are sorted first. This is a
        boost, not a filter — non-matching candidates still appear, just ranked
        lower. When entity_type is None, sorts by prior only (backward compatible).

        Pure read — no side effects. Returns an empty list if no candidates found.
        """
        candidates = self._lookup.get(mention.lower(), [])
        if entity_type is None:
            return sorted(candidates, key=lambda c: c.prior, reverse=True)

        # Type-matched first (1 sorts after 0 when reversed), then by prior
        return sorted(
            candidates,
            key=lambda c: (entity_type in c.entity_types, c.prior),
            reverse=True,
        )

    def stats(self) -> dict:
        """Return counts of entities, aliases, and total candidates."""
        total_candidates = sum(len(c) for c in self._lookup.values())
        return {
            "total_entities": self._entity_count,
            "total_aliases": len(self._lookup),
            "total_candidates": total_candidates,
        }
