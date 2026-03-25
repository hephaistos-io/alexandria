import { useMemo, useState, useCallback, useEffect } from "react";
import { formatDate } from "../../utils/formatDate";
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  useNodesState,
  useEdgesState,
  Position,
  BackgroundVariant,
} from "@xyflow/react";
import type { Node, Edge, NodeProps, NodeTypes, NodeMouseHandler } from "@xyflow/react";
import { MaterialIcon } from "../shared/MaterialIcon";
import type {
  ContainerStatus,
  QueueStatus,
  ExchangeStatus,
  DbStatus,
} from "../../types/infrastructure";
import { buildPipelineGraph } from "../../config/buildPipelineGraph";
import { useTopology } from "../../hooks/useTopology";

// ─── Node data shapes ────────────────────────────────────────────────────────
// Each custom node type carries a typed `data` object.
// The `nodeKind` field lets the detail panel know which lookup path to take.

interface ServiceNodeData extends Record<string, unknown> {
  label: string;
  sublabel: string;
  icon: string;
  accentColor: "primary" | "tertiary" | "error";
  active: boolean | undefined;
  containerName: string;
  containerInstance?: number;
  /** False for pipeline entry points (fetchers) that have no upstream node. */
  hasInput: boolean;
}

interface TransportNodeData extends Record<string, unknown> {
  label: string;
  sublabel: string;
  icon: string;
  variant: "primary" | "tertiary" | "error";
  glowing?: boolean;
  /** RabbitMQ queue name (for queue nodes and queue-backed outputs). */
  queueName?: string;
  /** RabbitMQ exchange name (for exchange nodes). */
  exchangeName?: string;
  /** Comma-separated fanout targets shown in the detail panel. */
  fansOutTo?: string;
  /** Named source handles (e.g. for exchange multi-output). When absent, a single unnamed output handle is rendered. */
  sourceHandles?: { id: string; top: string }[];
}

// ─── Custom node components ──────────────────────────────────────────────────
// Each receives NodeProps<Node<DataShape, TypeString>>.
// The outer div must be `nowheel` so scroll events don't propagate to the
// React Flow canvas (a React Flow convention).

type ServiceNodeType = Node<ServiceNodeData, "service">;

function ServiceNodeComponent({ data }: NodeProps<ServiceNodeType>) {
  const borderMap = {
    primary: "border-primary/50",
    tertiary: "border-tertiary/50",
    error: "border-error/40",
  };
  const iconMap = {
    primary: "text-primary",
    tertiary: "text-tertiary",
    error: "text-error/70",
  };
  const dimmed = data.active === false;

  return (
    <div
      className={`px-3 py-2.5 bg-surface-container border ${borderMap[data.accentColor]} flex items-center gap-2.5 nowheel cursor-pointer ${dimmed ? "opacity-40" : ""}`}
      style={{ width: 176 }}
    >
      {data.hasInput && (
        <Handle
          type="target"
          position={Position.Left}
          style={{ background: "#76a9fa", border: "none", width: 6, height: 6 }}
        />
      )}
      <MaterialIcon
        name={data.icon}
        className={`text-base ${iconMap[data.accentColor]}`}
      />
      <div className="flex-1 min-w-0">
        <div className="font-mono text-[10px] text-on-surface font-bold truncate">{data.label}</div>
        <div className="font-mono text-[9px] text-outline truncate">{data.sublabel}</div>
      </div>
      {data.active != null && (
        <span
          className={`w-1.5 h-1.5 shrink-0 rounded-full ${data.active ? "bg-tertiary animate-pulse" : "bg-outline/40"}`}
        />
      )}
      <Handle
        type="source"
        position={Position.Right}
        style={{ background: "#76a9fa", border: "none", width: 6, height: 6 }}
      />
    </div>
  );
}

type TransportNodeType = Node<TransportNodeData, "transport">;

function TransportNodeComponent({ data }: NodeProps<TransportNodeType>) {
  const borderMap = {
    primary: "border-primary",
    tertiary: "border-tertiary-container/40",
    error: "border-error/40",
  };
  const colorMap = {
    primary: "text-primary",
    tertiary: "text-tertiary",
    error: "text-error/70",
  };
  const handleColor =
    data.variant === "tertiary" ? "#5adace" : "#76a9fa";

  return (
    <div
      className={`p-4 bg-surface-container-high border-2 ${borderMap[data.variant]} flex flex-col items-center gap-1.5 ${data.glowing ? "glow-primary" : ""} nowheel cursor-pointer`}
      style={{ width: 120 }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: handleColor, border: "none", width: 6, height: 6 }}
      />
      <MaterialIcon name={data.icon} className={`${colorMap[data.variant]} text-xl`} />
      <span className={`font-mono text-[10px] font-bold ${colorMap[data.variant]} uppercase text-center`}>
        {data.label}
      </span>
      <span className="font-mono text-[9px] text-outline text-center">{data.sublabel}</span>
      {data.sourceHandles != null ? (
        data.sourceHandles.map((h) => (
          <Handle
            key={h.id}
            type="source"
            position={Position.Right}
            id={h.id}
            style={{ top: h.top, background: handleColor, border: "none", width: 6, height: 6 }}
          />
        ))
      ) : (
        <Handle
          type="source"
          position={Position.Right}
          style={{ background: handleColor, border: "none", width: 6, height: 6 }}
        />
      )}
    </div>
  );
}

// ─── Node type registry ──────────────────────────────────────────────────────
// This object is stable — defined outside the component so React Flow doesn't
// see a new reference on every render, which would cause unnecessary re-mounts.

const NODE_TYPES: NodeTypes = {
  service: ServiceNodeComponent,
  transport: TransportNodeComponent,
};

// ─── Legend ─────────────────────────────────────────────────────────────────

function Legend() {
  return (
    <div className="flex justify-between items-center mt-4 pt-4 border-t border-outline-variant/10">
      <div className="flex gap-6">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 bg-primary" />
          <span className="font-mono text-[9px] text-outline uppercase">Active Queue</span>
        </div>
        <div className="flex items-center gap-2">
          <svg width="16" height="8" className="shrink-0">
            <line
              x1="0"
              y1="4"
              x2="16"
              y2="4"
              stroke="#76a9fa"
              strokeWidth="1"
              strokeDasharray="3 2"
              opacity="0.5"
            />
          </svg>
          <span className="font-mono text-[9px] text-outline uppercase">Fanout Exchange</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 bg-tertiary" />
          <span className="font-mono text-[9px] text-outline uppercase">Live Signal</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 bg-error/60" />
          <span className="font-mono text-[9px] text-outline uppercase">Training Buffer</span>
        </div>
      </div>
      <div className="font-mono text-[10px] text-primary-container font-bold tracking-[0.2em]">
        RABBITMQ_TOPOLOGY_V1
      </div>
    </div>
  );
}

/**
 * Converts a raw second count into a compact human-readable string.
 * Examples: 90 → "1m 30s", 3700 → "1h 1m", 90000 → "1d 1h"
 */
function formatUptime(seconds: number): string {
  if (seconds <= 0) return "0s";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);

  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

// ─── Detail panel ────────────────────────────────────────────────────────────

interface DetailPanelProps {
  nodeId: string | null;
  nodeType: string | undefined;
  nodeData: Record<string, unknown>;
  containers: ContainerStatus[] | undefined;
  queues: QueueStatus[] | undefined;
  db: DbStatus | null | undefined;
  onClose: () => void;
}

/** One row in the detail panel — a label/value pair. */
function DetailRow({ label, value, valueClass = "text-primary" }: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5 border-b border-outline-variant/10 last:border-0">
      <span className="font-mono text-[9px] text-outline uppercase tracking-widest shrink-0">
        {label}
      </span>
      <span className={`font-mono text-[10px] font-bold ${valueClass} text-right`}>
        {value}
      </span>
    </div>
  );
}

/** Green/red status pill used in container sections. */
function StatusBadge({ status, health }: { status: string; health: string | null }) {
  const isRunning = status === "running";
  const isHealthy = health === "healthy" || health === null;
  const dotColor = isRunning && isHealthy ? "bg-tertiary animate-pulse" : "bg-error";
  const textColor = isRunning && isHealthy ? "text-tertiary" : "text-error";
  const label = isRunning
    ? (health != null ? health.toUpperCase() : "RUNNING")
    : status.toUpperCase();

  return (
    <div className="flex items-center gap-1.5">
      <span className={`w-1.5 h-1.5 shrink-0 ${dotColor}`} />
      <span className={`font-mono text-[10px] font-bold ${textColor} uppercase`}>{label}</span>
    </div>
  );
}

function ContainerDetails({
  containerName,
  containerInstance,
  containers,
}: {
  containerName: string;
  containerInstance?: number;
  containers: ContainerStatus[] | undefined;
}) {
  const container = containers?.find(
    (c) => c.name === containerName && (containerInstance == null || c.instance === containerInstance),
  );

  if (containers == null) {
    return (
      <p className="font-mono text-[9px] text-outline italic">Monitoring API unavailable</p>
    );
  }

  if (container == null) {
    return (
      <p className="font-mono text-[9px] text-outline italic">Container not found</p>
    );
  }

  return (
    <div className="flex flex-col gap-0">
      <div className="flex items-center justify-between pb-2 mb-1 border-b border-outline-variant/10">
        <span className="font-mono text-[9px] text-outline uppercase tracking-widest">Status</span>
        <StatusBadge status={container.status} health={container.health} />
      </div>
      <DetailRow label="Uptime" value={formatUptime(container.uptime_seconds)} />
      <DetailRow
        label="Restarts"
        value={String(container.restart_count)}
        valueClass={container.restart_count > 0 ? "text-error" : "text-primary"}
      />
    </div>
  );
}

function QueueDetails({
  queueName,
  queues,
}: {
  queueName: string;
  queues: QueueStatus[] | undefined;
}) {
  const queue = queues?.find((q) => q.name === queueName);

  if (queues == null) {
    return (
      <p className="font-mono text-[9px] text-outline italic">Monitoring API unavailable</p>
    );
  }

  if (queue == null) {
    return (
      <p className="font-mono text-[9px] text-outline italic">Queue not found</p>
    );
  }

  return (
    <div className="flex flex-col gap-0">
      <DetailRow label="Messages" value={String(queue.messages)} />
      <DetailRow label="Consumers" value={String(queue.consumers)} />
      <DetailRow
        label="Publish Rate"
        value={`${queue.publish_rate.toFixed(2)}/s`}
        valueClass="text-tertiary"
      />
      <DetailRow
        label="Deliver Rate"
        value={`${queue.deliver_rate.toFixed(2)}/s`}
        valueClass="text-tertiary"
      />
    </div>
  );
}

function DbDetails({ db }: { db: DbStatus | null | undefined }) {
  if (db == null) {
    return (
      <p className="font-mono text-[9px] text-outline italic">
        {db === null ? "No DB data available" : "Monitoring API unavailable"}
      </p>
    );
  }

  const latestInsert = db.latest_insert != null
    ? formatDate(db.latest_insert)
    : "—";

  return (
    <div className="flex flex-col gap-0">
      <DetailRow label="Articles" value={String(db.article_count)} />
      <DetailRow label="Labelled" value={String(db.labelled_count)} />
      <DetailRow label="Latest Insert" value={latestInsert} valueClass="text-outline" />
    </div>
  );
}

function NodeDetailPanel({
  nodeId,
  nodeType,
  nodeData,
  containers,
  queues,
  db,
  onClose,
}: DetailPanelProps) {
  const visible = nodeId != null;

  // Track whether the panel should be rendered in the DOM. Stays true for
  // 200ms after closing so the slide-out animation plays before we hide it.
  const [rendered, setRendered] = useState(false);
  useEffect(() => {
    if (visible) {
      setRendered(true);
    } else {
      const timer = setTimeout(() => setRendered(false), 200);
      return () => clearTimeout(timer);
    }
  }, [visible]);

  // Map node type to a section title and icon for the panel header.
  const headerMeta: Record<string, { title: string; icon: string; accentClass: string }> = {
    service: { title: "Service", icon: "memory", accentClass: "text-primary" },
    transport: { title: "Transport", icon: "dynamic_feed", accentClass: "text-primary" },
  };

  const meta = nodeType != null ? (headerMeta[nodeType] ?? headerMeta.transport) : headerMeta.transport;

  return (
    // Overlay panel — absolutely positioned over the right portion of the canvas.
    // The translate transform drives the slide-in / slide-out animation.
    <div
      className={`absolute top-0 right-0 h-full w-56 z-20 flex flex-col bg-surface-container-low border-l border-outline-variant/20 transition-transform duration-200 ease-out ${
        visible ? "translate-x-0" : "translate-x-full"
      } ${rendered ? "" : "hidden"}`}
      // Prevent mouse events from bubbling to React Flow when the panel is open.
      onMouseDown={(e) => e.stopPropagation()}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-outline-variant/15 bg-surface-container">
        <div className="flex items-center gap-2">
          <MaterialIcon name={meta.icon} className={`text-base ${meta.accentClass}`} />
          <div>
            <div className={`font-mono text-[9px] uppercase tracking-widest ${meta.accentClass}`}>
              {meta.title}
            </div>
            <div className="font-mono text-[10px] text-on-surface font-bold truncate max-w-32">
              {String(nodeData.label ?? "")}
            </div>
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-outline hover:text-on-surface transition-colors p-0.5"
          aria-label="Close detail panel"
        >
          <MaterialIcon name="close" className="text-sm" />
        </button>
      </div>

      {/* Content — scrollable if it overflows */}
      <div className="flex-1 overflow-y-auto px-3 py-3 flex flex-col gap-4">
        {nodeType === "service" && (
          <div>
            <div className="font-mono text-[9px] text-outline uppercase tracking-widest mb-2">
              Container
            </div>
            <ContainerDetails
              containerName={String(nodeData.containerName ?? "")}
              containerInstance={nodeData.containerInstance as number | undefined}
              containers={containers}
            />
          </div>
        )}

        {nodeType === "transport" && (
          <>
            {nodeData.exchangeName != null && (
              <div>
                <div className="font-mono text-[9px] text-outline uppercase tracking-widest mb-2">
                  Exchange Info
                </div>
                <div className="flex flex-col gap-0">
                  <DetailRow label="Type" value="FANOUT" valueClass="text-tertiary" />
                  <DetailRow label="Name" value={String(nodeData.exchangeName)} valueClass="text-outline" />
                  <div className="pt-2">
                    <div className="font-mono text-[9px] text-outline uppercase tracking-widest mb-1">
                      Fans out to
                    </div>
                    {String(nodeData.fansOutTo ?? "")
                      .split(",")
                      .map((q) => q.trim())
                      .filter(Boolean)
                      .map((q) => (
                        <div key={q} className="flex items-center gap-1.5 py-0.5">
                          <span className="w-1 h-1 bg-tertiary shrink-0" />
                          <span className="font-mono text-[9px] text-on-surface">{q}</span>
                        </div>
                      ))}
                  </div>
                </div>
              </div>
            )}
            {nodeData.queueName === "postgres" && (
              <div>
                <div className="font-mono text-[9px] text-outline uppercase tracking-widest mb-2">
                  Database
                </div>
                <DbDetails db={db} />
              </div>
            )}
            {nodeData.queueName != null && nodeData.queueName !== "postgres" && nodeData.exchangeName == null && (
              <div>
                <div className="font-mono text-[9px] text-outline uppercase tracking-widest mb-2">
                  Queue Stats
                </div>
                <QueueDetails
                  queueName={String(nodeData.queueName)}
                  queues={queues}
                />
              </div>
            )}
          </>
        )}
      </div>

      {/* Footer watermark */}
      <div className="px-3 py-2 border-t border-outline-variant/10">
        <div className="font-mono text-[8px] text-outline/30 uppercase tracking-widest">
          NODE_DETAIL_V1 // {nodeId ?? "—"}
        </div>
      </div>
    </div>
  );
}

// ─── Main component ──────────────────────────────────────────────────────────

interface PipelineFlowProps {
  containers?: ContainerStatus[];
  queues?: QueueStatus[];
  exchanges?: ExchangeStatus[];
  db?: DbStatus | null;
}

export function PipelineFlow({ containers, queues, exchanges, db }: PipelineFlowProps = {}) {
  const topology = useTopology();

  // Build nodes and edges dynamically from the topology config + live API data.
  // The graph builder resolves container/queue instances, computes layout
  // positions, and generates edges as a cartesian product of connected stages.
  const { nodes: computedNodes, edges: computedEdges } = useMemo(() => {
    if (topology == null) return { nodes: [], edges: [] };
    return buildPipelineGraph(
      topology,
      containers ?? [],
      queues ?? [],
      exchanges ?? [],
    );
  }, [topology, containers, queues, exchanges]);

  // useNodesState / useEdgesState give us the managed state React Flow needs
  // while still letting users drag nodes around.
  const [nodes, setNodes, onNodesChange] = useNodesState(computedNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(computedEdges);

  // useNodesState / useEdgesState only use their argument as the *initial*
  // value (like useState). When live data changes, we need to push the
  // updated nodes and edges explicitly.
  useEffect(() => {
    setNodes(computedNodes);
    setEdges(computedEdges);
  }, [computedNodes, computedEdges, setNodes, setEdges]);

  // ── Selected node state ──
  // We only store the node ID on click and derive type/data from the live
  // nodes array. This way the detail panel always shows current data instead
  // of a stale snapshot captured at click time.
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const selectedNode = selectedNodeId != null
    ? nodes.find((n) => n.id === selectedNodeId)
    : undefined;
  const selectedNodeType = selectedNode?.type;
  const selectedNodeData = (selectedNode?.data ?? {}) as Record<string, unknown>;

  const handleNodeClick: NodeMouseHandler = useCallback((_event, node) => {
    setSelectedNodeId(node.id);
  }, []);

  const handleClose = useCallback(() => {
    setSelectedNodeId(null);
  }, []);

  return (
    <div className="col-span-12 lg:col-span-9 bg-surface-container-low relative p-1 overflow-hidden">
      <div className="bg-surface-container-lowest h-full w-full min-h-[420px] p-6 flex flex-col relative overflow-hidden">
        {/* Corner labels */}
        <div className="absolute top-3 left-4 font-mono text-[10px] text-outline/30 uppercase select-none z-10 pointer-events-none">
          [ FLOW_SCHEMATIC_V1.0 ]
        </div>
        <div className="absolute bottom-16 right-4 font-mono text-[10px] text-outline/30 select-none z-10 pointer-events-none">
          RABBITMQ_TRANSPORT // FANOUT_EXCHANGE
        </div>

        {/* Loading overlay — shown until /api/topology responds */}
        {topology == null && (
          <div className="absolute inset-0 z-30 flex items-center justify-center bg-surface-container-lowest/80">
            <span className="font-mono text-[10px] text-outline uppercase tracking-widest animate-pulse">
              Loading topology...
            </span>
          </div>
        )}

        {/* React Flow canvas — wrapped in a relative container so the panel
            can be absolutely positioned over it without escaping the card */}
        <div className="flex-1 relative" style={{ minHeight: 340 }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={NODE_TYPES}
            onNodeClick={handleNodeClick}
            // Clicking on the pane (empty canvas area) closes the panel.
            onPaneClick={handleClose}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            minZoom={0.3}
            maxZoom={2}
            panOnDrag
            zoomOnScroll
            nodesConnectable={false}
            // elementsSelectable must be true for onNodeClick to fire.
            elementsSelectable={true}
            colorMode="dark"
          >
            <Background
              variant={BackgroundVariant.Dots}
              gap={24}
              size={1}
              color="rgba(118, 169, 250, 0.08)"
            />
            <Controls
              showInteractive={false}
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 1,
              }}
            />
          </ReactFlow>

          {/* Detail panel — slides in from the right over the canvas */}
          <NodeDetailPanel
            nodeId={selectedNodeId}
            nodeType={selectedNodeType}
            nodeData={selectedNodeData}
            containers={containers}
            queues={queues}
            db={db}
            onClose={handleClose}
          />
        </div>

        <Legend />
      </div>
    </div>
  );
}
