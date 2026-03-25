// ─── Pipeline topology configuration ──────────────────────────────────────────
// Defines the shape of the Alexandria OSINT pipeline declaratively.
// The visualization builds nodes and edges dynamically from this config
// plus the live API data from /api/status.
//
// To add a new pipeline stage: add an entry to `stages` and the appropriate
// connections. The layout engine handles positioning automatically.

// ─── Types ───────────────────────────────────────────────────────────────────

/** How a stage discovers its instances from the API response. */
export interface StageMatch {
  /** Match containers whose service name equals this value exactly.
   *  If the string ends with "-", it acts as a prefix match instead —
   *  this is how we discover all article-fetcher-* variants. */
  service?: string;
  /** Match a RabbitMQ queue by exact name. */
  queue?: string;
  /** Match a RabbitMQ exchange by exact name. */
  exchange?: string;
}

/** Visual properties for a stage's nodes. */
export interface StageVisual {
  nodeType: "service" | "transport";
  label: string;
  sublabel?: string;
  icon?: string;
  accentColor?: "primary" | "tertiary" | "error";
  variant?: "primary" | "tertiary" | "error";
  glowing?: boolean;
  /** Whether the node has an input (target) handle. Defaults to true.
   *  Set to false for pipeline entry points like fetchers. */
  hasInput?: boolean;
  /** Named source handles for multi-output nodes (e.g. fanout exchange). */
  sourceHandles?: { id: string; top: string }[];
}

/** A logical step in the data pipeline. */
export interface PipelineStage {
  id: string;
  /** Column index (0-based, left to right). Multiple stages can share a column. */
  column: number;
  match: StageMatch;
  visual: StageVisual;
  /** When true, multiple containers matching this stage each get their own node. */
  scalable: boolean;
}

/** A directed connection between two stages. */
export interface StageConnection {
  from: string;
  to: string;
  /** Named source handle on the 'from' node (used for exchange multi-output). */
  sourceHandle?: string;
  dashed?: boolean;
  /** Edge colour. Defaults to "#76a9fa" (blue). */
  color?: string;
}

export interface PipelineTopology {
  stages: PipelineStage[];
  connections: StageConnection[];
}

