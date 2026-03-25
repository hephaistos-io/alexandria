import type { InfraStatus } from "../../types/infrastructure";

interface SystemStatusFloatProps {
  status: InfraStatus | null;
}

// Filter out the "base" build-only container — it always exits immediately
// and isn't a real service. Everything else counts toward the ratio.
const EXCLUDED_CONTAINERS = new Set(["base"]);

function formatTimeSince(isoDate: string): string {
  const ms = Date.now() - new Date(isoDate).getTime();
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function SystemStatusFloat({ status }: SystemStatusFloatProps) {
  // Derive metrics from live infra data.
  const containers = (status?.containers ?? []).filter(
    (c) => !EXCLUDED_CONTAINERS.has(c.name),
  );
  const runningCount = containers.filter((c) => c.status === "running").length;
  const totalCount = containers.length;

  const queues = status?.queues ?? [];
  const totalMessages = queues.reduce((sum, q) => sum + q.messages, 0);
  const totalPublishRate = queues.reduce((sum, q) => sum + q.publish_rate, 0);
  const totalDeliverRate = queues.reduce((sum, q) => sum + q.deliver_rate, 0);

  // Throughput: what % of incoming messages are being consumed.
  // If nothing is being published, throughput is 100% (no backlog building).
  const throughputPct =
    totalPublishRate > 0
      ? Math.min(100, Math.round((totalDeliverRate / totalPublishRate) * 100))
      : 100;

  // Pipeline status label + color.
  const pipelineLabel =
    totalCount === 0
      ? "OFFLINE"
      : runningCount === totalCount
        ? "NOMINAL"
        : "DEGRADED";

  const statusDotColor =
    pipelineLabel === "NOMINAL"
      ? "bg-tertiary"
      : pipelineLabel === "DEGRADED"
        ? "bg-warning"
        : "bg-error";

  const statusDotPulse = pipelineLabel !== "NOMINAL" ? "animate-pulse" : "";

  const db = status?.db;

  return (
    <div className="fixed bottom-6 left-72 z-[500] bg-surface-container-high/80 backdrop-blur-md border border-outline-variant/30 p-4 w-80 shadow-[0_0_20px_rgba(118,169,250,0.1)]">
      {/* Title row with status dot */}
      <div className="flex items-center gap-2 mb-3">
        <div className={`w-1.5 h-1.5 rounded-full ${statusDotColor} ${statusDotPulse}`} />
        <span className="font-mono text-[9px] text-outline uppercase">
          PIPELINE_STATUS: {pipelineLabel}
        </span>
      </div>

      {/* Throughput bar — shows what % of published messages are being consumed */}
      <div className="h-1 bg-surface-container-lowest mb-4 overflow-hidden">
        <div
          className="h-full bg-primary-container shadow-[0_0_8px_#76a9fa] transition-all duration-700"
          style={{ width: `${throughputPct}%` }}
        />
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="font-mono text-[9px] text-outline mb-1">
            QUEUE_DEPTH
          </div>
          <div className={`font-mono text-sm ${totalMessages > 50 ? "text-warning" : "text-on-surface"}`}>
            {totalMessages.toLocaleString()} msg
          </div>
        </div>
        <div>
          <div className="font-mono text-[9px] text-outline mb-1">
            ACTIVE_SERVICES
          </div>
          <div className={`font-mono text-sm ${runningCount < totalCount ? "text-warning" : "text-on-surface"}`}>
            {runningCount}/{totalCount}
          </div>
        </div>
        <div>
          <div className="font-mono text-[9px] text-outline mb-1">
            ARTICLES_INGESTED
          </div>
          <div className="font-mono text-sm text-on-surface">
            {db?.article_count?.toLocaleString() ?? "—"}
          </div>
        </div>
        <div>
          <div className="font-mono text-[9px] text-outline mb-1">
            LAST_INGEST
          </div>
          <div className="font-mono text-sm text-on-surface">
            {db?.latest_insert ? formatTimeSince(db.latest_insert) : "—"}
          </div>
        </div>
      </div>
    </div>
  );
}
