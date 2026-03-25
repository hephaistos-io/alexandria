import type { DbStatus, QueueStatus, ContainerStatus } from "../../types/infrastructure";

const DELTA_CLASS = {
  tertiary: "text-tertiary",
  error: "text-error",
  outline: "text-outline",
} as const;

interface InfraMetric {
  label: string;
  value: string;
  delta: string;
  deltaColor: "tertiary" | "error" | "outline";
}

interface InfraMetricsRowProps {
  db?: DbStatus | null;
  queues?: QueueStatus[];
  containers?: ContainerStatus[];
}

function deriveMetrics(
  db: DbStatus | null | undefined,
  queues: QueueStatus[] | undefined,
  containers: ContainerStatus[] | undefined,
): InfraMetric[] {
  const articlesStored = db != null ? String(db.article_count) : "—";
  const queueDepth =
    queues != null ? String(queues.reduce((sum, q) => sum + q.messages, 0)) : "—";
  const activeServices =
    containers != null
      ? String(containers.filter((c) => c.status === "running").length)
      : "—";
  const labelsApplied = db != null ? String(db.labelled_count) : "0";

  return [
    {
      label: "Articles Stored",
      value: articlesStored,
      delta: db != null && db.latest_insert != null ? "Latest insert" : "No data",
      deltaColor: db != null ? "tertiary" : "outline",
    },
    {
      label: "Queue Depth",
      value: queueDepth,
      delta: queueDepth === "0" ? "Idle" : "Pending",
      deltaColor: queueDepth === "0" ? "outline" : "tertiary",
    },
    {
      label: "Active Services",
      value: activeServices,
      delta: "Running",
      deltaColor: "tertiary",
    },
    {
      label: "Labels Applied",
      value: labelsApplied,
      delta: labelsApplied === "0" ? "None yet" : "Labelled",
      deltaColor: labelsApplied === "0" ? "outline" : "tertiary",
    },
  ];
}

export function InfraMetricsRow({ db, queues, containers }: InfraMetricsRowProps = {}) {
  const metrics = deriveMetrics(db, queues, containers);

  return (
    <div className="col-span-12 grid grid-cols-2 md:grid-cols-4 gap-6">
      {metrics.map((metric) => (
        <div
          key={metric.label}
          className="bg-surface-container-low p-4 border border-outline-variant/10"
        >
          <div className="font-mono text-[10px] text-outline uppercase tracking-widest mb-2">
            {metric.label}
          </div>
          <div className="flex items-end gap-2">
            <span className="text-2xl font-mono text-primary font-bold">{metric.value}</span>
            <span className={`text-[10px] font-mono mb-1 ${DELTA_CLASS[metric.deltaColor]}`}>
              {metric.delta}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
