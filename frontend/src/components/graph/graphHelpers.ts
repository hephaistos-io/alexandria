import type { RelationType } from "../../types/graph";

// ── Graph node/link types for ForceGraph2D ────────────────────────────────────

// ForceGraph2D adds runtime fields (x, y, vx, vy) to nodes.
// We extend our domain type with those so TypeScript stays happy.
export interface FGNode {
  id: string;
  name: string;
  entity_type: string;
  // Injected at runtime by force-graph
  x?: number;
  y?: number;
  [key: string]: unknown;
}

export interface FGLink {
  source: string | FGNode;
  target: string | FGNode;
  relation_type: string;
  display_strength: number;
  curvature?: number;
  [key: string]: unknown;
}

// ── Helper functions ──────────────────────────────────────────────────────────

// Maps entity type strings to their display colors.
// These colors are drawn from the project's existing palette.
export function entityTypeColor(entityType: string): string {
  switch (entityType.toUpperCase()) {
    case "GPE":
      return "#a9c7ff"; // primary blue
    case "ORG":
    case "ORGANIZATION":
      return "#c084fc"; // purple
    case "PERSON":
      return "#5adace"; // tertiary teal
    case "LOC":
    case "LOCATION":
      return "#76a9fa"; // primary-container
    case "FAC":
      return "#f9a8d4"; // pink
    default:
      return "#8c919c"; // outline grey
  }
}

// Given a list of relation types, build a Map from uppercased name -> hex color.
// Falls back to a dim grey so the graph still renders with no schema loaded.
export function buildRelationColorMap(relationTypes: RelationType[]): Map<string, string> {
  const map = new Map<string, string>();
  for (const rt of relationTypes) {
    map.set(rt.name.toUpperCase(), `#${rt.color.replace(/^#/, "")}`);
  }
  return map;
}

// Compute the temporal half-life from lambda (λ): t½ = ln(2) / λ
// This lets users understand intuitively what the decay slider means.
export function halfLifeDays(lambda: number): string {
  const days = Math.log(2) / lambda;
  if (days >= 365) return `${(days / 365).toFixed(1)}yr`;
  if (days >= 30) return `${(days / 30).toFixed(1)}mo`;
  return `${Math.round(days)}d`;
}

// Resolve a ForceGraph2D edge endpoint to its string ID.
// The library replaces string IDs with full node objects after the first render,
// so we have to handle both cases wherever we read source/target.
export function resolveNodeId(endpoint: string | FGNode): string {
  return typeof endpoint === "string" ? endpoint : endpoint.id;
}
