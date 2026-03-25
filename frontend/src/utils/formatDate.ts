/**
 * Formats a date string into a canonical UTC timestamp for display.
 *
 * Returns "—" for null/empty input. Returns the raw string if the value
 * cannot be parsed as a date, so callers never see a blank or thrown error.
 *
 * Output format: "2024-03-15 14:30 UTC"
 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  // new Date() sets d.getTime() to NaN when the string is unparseable.
  if (isNaN(d.getTime())) return iso;
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
}
