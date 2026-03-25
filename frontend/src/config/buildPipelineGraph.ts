// ─── Pipeline graph builder ──────────────────────────────────────────────────
// Takes the declarative topology config plus live API data and produces
// React Flow Node[] and Edge[] arrays. This is a pure function — no hooks,
// no side effects — which makes it easy to test and reason about.
//
// The three main steps:
//   1. Resolve instances — match each topology stage against the API data
//   2. Compute layout    — assign x,y positions (column-based, vertically centered)
//   3. Build edges       — cartesian product of connected stage instances

import type { Node, Edge } from "@xyflow/react";
import type {
  ContainerStatus,
  QueueStatus,
  ExchangeStatus,
} from "../types/infrastructure";
import type {
  PipelineTopology,
  PipelineStage,
  StageConnection,
} from "./pipelineTopology";

// ─── Layout constants ────────────────────────────────────────────────────────

/** Horizontal distance between pipeline columns. */
const COL_WIDTH = 300;

/** Approximate height of one node (for vertical spacing). */
const NODE_HEIGHT = 80;

/** Gap between vertically stacked nodes in the same column. */
const NODE_GAP = 20;

/** Vertical midpoint — columns are centered around this y value. */
const CANVAS_MID_Y = 200;

// ─── Resolved instance ──────────────────────────────────────────────────────

/** One concrete node to render, produced by matching a stage against API data. */
interface ResolvedInstance {
  /** Back-reference to the topology stage this came from. */
  stageId: string;
  /** Unique React Flow node ID. */
  nodeId: string;
  /** Display label (e.g. "BBC", "article-scraper #2"). */
  label: string;
  /** Display sublabel (e.g. "0 messages", "HTML → content"). */
  sublabel: string;
  /** For container-backed nodes: service name for detail panel lookup. */
  containerName?: string;
  /** For container-backed nodes: instance number for detail panel lookup. */
  containerInstance?: number;
  /** For queue-backed nodes: queue name for detail panel lookup. */
  queueName?: string;
  /** For exchange nodes: exchange name for detail panel lookup. */
  exchangeName?: string;
  /** Whether the container is running (undefined = data not available). */
  active?: boolean | undefined;
}

// ─── Instance resolution ─────────────────────────────────────────────────────

function resolveInstances(
  stage: PipelineStage,
  containers: ContainerStatus[],
  queues: QueueStatus[],
  _exchanges: ExchangeStatus[],
): ResolvedInstance[] {
  const { match, visual, id } = stage;

  // Queue match — one node per queue (queues are not scaled).
  if (match.queue != null) {
    const q = queues.find((q) => q.name === match.queue);
    return [
      {
        stageId: id,
        nodeId: id,
        label: visual.label,
        sublabel: q != null ? `${q.messages} messages` : "AMQP queue",
        queueName: match.queue,
      },
    ];
  }

  // Exchange match — one node per exchange.
  if (match.exchange != null) {
    // Build the "fans out to" string by looking at the topology connections
    // that originate from this exchange stage. We'll populate this in the
    // main buildPipelineGraph function instead, since we need the full topology.
    return [
      {
        stageId: id,
        nodeId: id,
        label: visual.label,
        sublabel: visual.sublabel ?? "exchange",
        exchangeName: match.exchange,
      },
    ];
  }

  // Service match — the interesting case. Can match multiple containers.
  if (match.service != null) {
    const isPrefix = match.service.endsWith("-");
    const matched = containers.filter((c) =>
      isPrefix ? c.name.startsWith(match.service!) : c.name === match.service,
    );

    if (matched.length === 0) {
      // No containers running — show a single dimmed placeholder.
      return [
        {
          stageId: id,
          nodeId: id,
          label: visual.label,
          sublabel: "not running",
          containerName: isPrefix ? match.service.slice(0, -1) : match.service,
          active: false,
        },
      ];
    }

    return matched.map((c) => {
      // For prefix-matched services (fetchers), derive label from the suffix.
      // e.g. "article-fetcher-bbc" with prefix "article-fetcher-" → "BBC"
      const suffix = c.name.replace(match.service!, "");
      const displayLabel = isPrefix
        ? suffix.toUpperCase()
        : matched.length > 1
          ? `${visual.label} #${c.instance}`
          : visual.label;

      const displaySublabel = isPrefix ? c.name : (visual.sublabel ?? "");

      // Node IDs must be unique. Prefix-matched services are different
      // services (e.g. article-fetcher-bbc vs -swissinfo) so we use the
      // name suffix. Exact-matched services are scaled replicas so we
      // use the instance number.
      const nodeId = matched.length > 1
        ? isPrefix ? `${id}-${suffix}` : `${id}-${c.instance}`
        : id;

      return {
        stageId: id,
        nodeId,
        label: displayLabel,
        sublabel: displaySublabel,
        containerName: c.name,
        containerInstance: c.instance,
        active: c.status === "running",
      };
    });
  }

  return [];
}

// ─── Layout calculation ──────────────────────────────────────────────────────

interface ColumnSlot {
  nodeId: string;
  column: number;
  /** Position within the column (0-indexed). */
  row: number;
  /** True for infrastructure nodes (stores, monitoring) placed below the pipeline. */
  isInfra: boolean;
  /** "service" or "transport" — transport nodes are offset to their own row. */
  nodeType: "service" | "transport";
}

/** Vertical gap between the service row and the transport row. */
const TRANSPORT_ROW_GAP = 40;

/** Vertical gap between the bottom of the pipeline rows and the infra row. */
const INFRA_ROW_GAP = 60;

function layoutRow(
  slots: ColumnSlot[],
  centerY: number,
  xOffset: number,
): { positions: Map<string, { x: number; y: number }>; maxY: number } {
  const byColumn = new Map<number, ColumnSlot[]>();
  for (const slot of slots) {
    const list = byColumn.get(slot.column) ?? [];
    list.push(slot);
    byColumn.set(slot.column, list);
  }

  const positions = new Map<string, { x: number; y: number }>();
  let maxY = centerY;

  for (const [col, columnSlots] of byColumn) {
    const x = col * COL_WIDTH + xOffset;
    const count = columnSlots.length;
    const totalHeight = count * NODE_HEIGHT + (count - 1) * NODE_GAP;
    const startY = centerY - totalHeight / 2;

    columnSlots.sort((a, b) => a.row - b.row);

    for (let i = 0; i < columnSlots.length; i++) {
      const y = startY + i * (NODE_HEIGHT + NODE_GAP);
      positions.set(columnSlots[i].nodeId, { x, y });
      maxY = Math.max(maxY, y + NODE_HEIGHT);
    }
  }

  return { positions, maxY };
}

function computePositions(
  slots: ColumnSlot[],
): Map<string, { x: number; y: number }> {
  const serviceSlots = slots.filter((s) => !s.isInfra && s.nodeType === "service");
  const transportSlots = slots.filter((s) => !s.isInfra && s.nodeType === "transport");
  const infraSlots = slots.filter((s) => s.isInfra);

  const allPositions = new Map<string, { x: number; y: number }>();

  // --- Transport nodes: top row, offset a quarter column right ---
  const { positions: transportPos, maxY: transportMaxY } =
    layoutRow(transportSlots, CANVAS_MID_Y, COL_WIDTH / 4);

  // --- Service nodes: middle row, below transports ---
  const serviceCenterY = transportMaxY + TRANSPORT_ROW_GAP + NODE_HEIGHT / 2;
  const { positions: servicePos, maxY: serviceMaxY } =
    layoutRow(serviceSlots, serviceCenterY, 0);

  // --- Infra nodes: bottom row ---
  const infraCenterY = serviceMaxY + INFRA_ROW_GAP + NODE_HEIGHT / 2;
  const { positions: infraPos } =
    layoutRow(infraSlots, infraCenterY, 0);

  for (const [k, v] of servicePos) allPositions.set(k, v);
  for (const [k, v] of transportPos) allPositions.set(k, v);
  for (const [k, v] of infraPos) allPositions.set(k, v);

  return allPositions;
}

// ─── Edge generation ─────────────────────────────────────────────────────────

function buildEdges(
  connections: StageConnection[],
  instancesByStage: Map<string, ResolvedInstance[]>,
): Edge[] {
  const edges: Edge[] = [];
  const defaultColor = "#76a9fa";

  for (const conn of connections) {
    const fromInstances = instancesByStage.get(conn.from) ?? [];
    const toInstances = instancesByStage.get(conn.to) ?? [];

    const style: Record<string, unknown> = {
      stroke: conn.color ?? defaultColor,
      strokeWidth: 1,
      opacity: conn.dashed ? 0.7 : 0.6,
    };
    if (conn.dashed) {
      style.strokeDasharray = "5 3";
    }

    // Cartesian product: one edge per (from-instance, to-instance) pair.
    // This naturally handles fan-in and fan-out:
    //   2 fetchers → 1 queue = 2 edges
    //   1 queue → 3 scrapers = 3 edges
    for (const from of fromInstances) {
      for (const to of toInstances) {
        edges.push({
          id: `${from.nodeId}-${to.nodeId}`,
          source: from.nodeId,
          target: to.nodeId,
          type: "default",
          style,
          ...(conn.sourceHandle != null ? { sourceHandle: conn.sourceHandle } : {}),
        });
      }
    }
  }

  return edges;
}

// ─── Node data builder ───────────────────────────────────────────────────────
// Translates a ResolvedInstance into the data shape that each custom React Flow
// node component expects (ServiceNodeData, TransportNodeData).

function buildNodeData(
  stage: PipelineStage,
  instance: ResolvedInstance,
  fansOutTo: string,
): Record<string, unknown> {
  const { visual } = stage;

  switch (visual.nodeType) {
    case "service":
      return {
        label: instance.label,
        sublabel: instance.sublabel,
        icon: visual.icon ?? "memory",
        accentColor: visual.accentColor ?? "primary",
        active: instance.active,
        containerName: instance.containerName ?? "",
        containerInstance: instance.containerInstance,
        hasInput: visual.hasInput ?? true,
      };

    case "transport":
      return {
        label: instance.label,
        sublabel: instance.sublabel,
        icon: visual.icon ?? "inbox",
        variant: visual.variant ?? "primary",
        glowing: visual.glowing ?? false,
        queueName: instance.queueName,
        exchangeName: instance.exchangeName,
        fansOutTo: instance.exchangeName != null ? fansOutTo : undefined,
        sourceHandles: visual.sourceHandles,
      };

    default:
      return { label: instance.label, sublabel: instance.sublabel };
  }
}

// ─── Main export ─────────────────────────────────────────────────────────────

export function buildPipelineGraph(
  topology: PipelineTopology,
  containers: ContainerStatus[],
  queues: QueueStatus[],
  exchanges: ExchangeStatus[],
): { nodes: Node[]; edges: Edge[] } {
  // 1a. Identify infrastructure stages — service nodes where every connection
  //     is dashed (stores, monitoring, frontend). These get placed in a
  //     separate row below the main pipeline instead of cluttering column 0.
  const infraStageIds = new Set<string>();
  for (const stage of topology.stages) {
    if (stage.match.queue != null || stage.match.exchange != null) continue;
    const conns = topology.connections.filter(
      (c) => c.from === stage.id || c.to === stage.id,
    );
    if (conns.length > 0 && conns.every((c) => c.dashed === true)) {
      infraStageIds.add(stage.id);
    }
  }

  // 1b. Compute better columns for infra nodes based on their connected
  //     pipeline neighbours, so dashed edges stay short.
  const infraColumnOverride = new Map<string, number>();

  // Pass 1: infra nodes connected to at least one pipeline node.
  for (const stageId of infraStageIds) {
    const neighborIds = topology.connections
      .filter((c) => c.from === stageId || c.to === stageId)
      .map((c) => (c.from === stageId ? c.to : c.from));
    const pipelineNeighbors = neighborIds
      .map((id) => topology.stages.find((s) => s.id === id))
      .filter(
        (s): s is PipelineStage => s != null && !infraStageIds.has(s.id),
      );

    if (pipelineNeighbors.length > 0) {
      const avg =
        pipelineNeighbors.reduce((sum, s) => sum + s.column, 0) /
        pipelineNeighbors.length;
      infraColumnOverride.set(stageId, Math.round(avg));
    }
  }

  // Pass 2: infra nodes connected only to other infra nodes (e.g. frontend
  //         → monitoring-api). Use the positions resolved in pass 1.
  for (const stageId of infraStageIds) {
    if (infraColumnOverride.has(stageId)) continue;
    const neighborIds = topology.connections
      .filter((c) => c.from === stageId || c.to === stageId)
      .map((c) => (c.from === stageId ? c.to : c.from));
    const resolvedNeighbors = neighborIds.filter((id) =>
      infraColumnOverride.has(id),
    );

    if (resolvedNeighbors.length > 0) {
      const avg =
        resolvedNeighbors.reduce(
          (sum, id) => sum + infraColumnOverride.get(id)!,
          0,
        ) / resolvedNeighbors.length;
      infraColumnOverride.set(stageId, Math.round(avg));
    }
  }

  // 1c. Resolve instances for each stage.
  const instancesByStage = new Map<string, ResolvedInstance[]>();
  const allSlots: ColumnSlot[] = [];
  const rowCounterByColumn = new Map<number, number>();
  const infraRowCounterByColumn = new Map<number, number>();

  for (const stage of topology.stages) {
    const instances = resolveInstances(stage, containers, queues, exchanges);
    instancesByStage.set(stage.id, instances);

    const isInfra = infraStageIds.has(stage.id);
    const column = infraColumnOverride.get(stage.id) ?? stage.column;
    const counter = isInfra ? infraRowCounterByColumn : rowCounterByColumn;

    for (const inst of instances) {
      const currentRow = counter.get(column) ?? 0;
      allSlots.push({
        nodeId: inst.nodeId,
        column,
        row: currentRow,
        isInfra,
        nodeType: stage.visual.nodeType,
      });
      counter.set(column, currentRow + 1);
    }
  }

  // 2. Compute positions.
  const positions = computePositions(allSlots);

  // 3. Build the "fans out to" string for exchange nodes by looking at
  //    which stages the exchange connects to in the topology.
  const fansOutToByStage = new Map<string, string>();
  for (const conn of topology.connections) {
    if (fansOutToByStage.has(conn.from)) {
      fansOutToByStage.set(
        conn.from,
        fansOutToByStage.get(conn.from) + ", " + conn.to,
      );
    } else {
      fansOutToByStage.set(conn.from, conn.to);
    }
  }

  // 4. Build React Flow nodes.
  const nodes: Node[] = [];
  for (const stage of topology.stages) {
    const instances = instancesByStage.get(stage.id) ?? [];

    // For exchange nodes, resolve "fans out to" using the target stage labels.
    let fansOutTo = "";
    if (stage.match.exchange != null) {
      const targetStageIds = (fansOutToByStage.get(stage.id) ?? "").split(", ");
      const targetLabels = targetStageIds
        .map((sid) => {
          const targetStage = topology.stages.find((s) => s.id === sid);
          return targetStage?.visual.label ?? sid;
        })
        .filter(Boolean);
      fansOutTo = targetLabels.join(", ");
    }

    for (const inst of instances) {
      const pos = positions.get(inst.nodeId) ?? { x: 0, y: 0 };
      const data = buildNodeData(stage, inst, fansOutTo);

      nodes.push({
        id: inst.nodeId,
        type: stage.visual.nodeType,
        position: pos,
        data,
      });
    }
  }

  // 5. Build edges.
  const edges = buildEdges(topology.connections, instancesByStage);

  return { nodes, edges };
}
