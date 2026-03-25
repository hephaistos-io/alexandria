import type { AttributionEntity } from "../../types/attribution";

// The geographic NER labels we care about for role assignment.
// GPE = geopolitical entity, LOC = location, FAC = facility.
export const GEO_LABELS = new Set(["GPE", "LOC", "FAC"]);

// Build the dict key for an entity — mirrors what the backend uses so
// that manual_entity_roles keys round-trip correctly.
export function entityKey(entity: AttributionEntity): string {
  return entity.wikidata_id ?? entity.canonical_name ?? entity.text;
}
