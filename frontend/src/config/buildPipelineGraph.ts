// ─── Pipeline graph builder ──────────────────────────────────────────────────
// Takes the declarative topology config plus live API data and produces
// React Flow Node[] and Edge[] arrays. This is a pure function — no hooks,
// no side effects — which makes it easy to test and reason about.
//
// Layout is delegated to dagre (a directed-graph layout algorithm).
// We feed it the nodes and edges and it computes x,y positions automatically.

import Dagre from "@dagrejs/dagre";
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
      const suffix = c.name.replace(match.service!, "");
      const displayLabel = isPrefix
        ? suffix.toUpperCase()
        : matched.length > 1
          ? `${visual.label} #${c.instance}`
          : visual.label;

      const displaySublabel = isPrefix ? c.name : (visual.sublabel ?? "");

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

// ─── Dagre auto-layout ──────────────────────────────────────────────────────

/** Estimated node dimensions for dagre spacing. */
const NODE_WIDTH: Record<string, number> = {
  service: 176,
  transport: 120,
};
const NODE_HEIGHT = 80;

function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new Dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 40, ranksep: 120 });

  for (const node of nodes) {
    const w = NODE_WIDTH[node.type ?? "service"] ?? 176;
    g.setNode(node.id, { width: w, height: NODE_HEIGHT });
  }

  for (const edge of edges) {
    g.setEdge(edge.source, edge.target);
  }

  Dagre.layout(g);

  return nodes.map((node) => {
    const pos = g.node(node.id);
    const w = NODE_WIDTH[node.type ?? "service"] ?? 176;
    return {
      ...node,
      position: { x: pos.x - w / 2, y: pos.y - NODE_HEIGHT / 2 },
    };
  });
}

// ─── Main export ─────────────────────────────────────────────────────────────

export function buildPipelineGraph(
  topology: PipelineTopology,
  containers: ContainerStatus[],
  queues: QueueStatus[],
  exchanges: ExchangeStatus[],
): { nodes: Node[]; edges: Edge[] } {
  // 1. Resolve instances for each stage.
  const instancesByStage = new Map<string, ResolvedInstance[]>();

  for (const stage of topology.stages) {
    const instances = resolveInstances(stage, containers, queues, exchanges);
    instancesByStage.set(stage.id, instances);
  }

  // 2. Build the "fans out to" string for exchange nodes.
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

  // 3. Build React Flow nodes (positions will be set by dagre).
  const nodes: Node[] = [];
  for (const stage of topology.stages) {
    const instances = instancesByStage.get(stage.id) ?? [];

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
      const data = buildNodeData(stage, inst, fansOutTo);

      nodes.push({
        id: inst.nodeId,
        type: stage.visual.nodeType,
        position: { x: 0, y: 0 },
        data,
      });
    }
  }

  // 4. Build edges.
  const edges = buildEdges(topology.connections, instancesByStage);

  // 5. Auto-layout with dagre.
  const laidOutNodes = applyDagreLayout(nodes, edges);

  return { nodes: laidOutNodes, edges };
}
