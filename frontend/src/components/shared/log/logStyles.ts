// ── Level styling ─────────────────────────────────────────────────────────────

// Using a plain object rather than a Map so TypeScript can verify exhaustiveness
// via index access. Unknown levels fall back to the default text colour below.
export const LEVEL_CLASS: Record<string, string> = {
  info: "text-on-surface/80",
  debug: "text-on-surface/40",
  warning: "text-amber-400",
  error: "text-error",
};

export function levelClass(level: string): string {
  return LEVEL_CLASS[level] ?? "text-on-surface/60";
}

// ── Service badge colours ─────────────────────────────────────────────────────

// Each service name is hashed to one of these Tailwind bg/text pairs so the
// colour assignment is deterministic without requiring a lookup table that
// needs updating every time a new service is added.
export const SERVICE_PALETTE = [
  "bg-primary/20 text-primary",
  "bg-tertiary/20 text-tertiary",
  "bg-amber-400/15 text-amber-400",
  "bg-cyan-400/15 text-cyan-400",
  "bg-purple-400/15 text-purple-400",
  "bg-rose-400/15 text-rose-400",
  "bg-lime-400/15 text-lime-400",
  "bg-sky-400/15 text-sky-400",
];

// djb2-style hash — fast, good enough distribution for a handful of services.
export function djb2(str: string): number {
  let hash = 5381;
  for (let i = 0; i < str.length; i++) {
    hash = (hash * 33) ^ str.charCodeAt(i);
    hash = hash >>> 0; // keep it a 32-bit unsigned integer
  }
  return hash;
}

export function serviceColour(service: string): string {
  return SERVICE_PALETTE[djb2(service) % SERVICE_PALETTE.length];
}

// ── Timestamp formatting ──────────────────────────────────────────────────────

// Strips the date portion from an ISO timestamp, leaving only the time.
// e.g. "2024-03-21T14:22:01.440Z" → "14:22:01.440"
export function formatTimestamp(ts: string): string {
  if (ts.includes("T")) {
    return ts.split("T")[1].replace("Z", "").slice(0, 12);
  }
  return ts;
}
