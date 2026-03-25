/**
 * Converts a numeric article ID into the canonical reference ID used
 * throughout the UI and backend.
 *
 * The ID is encoded as a zero-padded 5-digit uppercase hex number.
 * Example: buildRefId(4271) → "ART-010AF"
 */
export function buildRefId(id: number): string {
  return `ART-${id.toString(16).toUpperCase().padStart(5, "0")}`;
}
