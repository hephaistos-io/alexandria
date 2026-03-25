import { useMemo } from "react";
import { useInfraStatus } from "../hooks/useInfraStatus";
import { useTopology } from "../hooks/useTopology";
import { InfraMetricsRow } from "../components/infrastructure/InfraMetricsRow";
import { PipelineFlow } from "../components/infrastructure/PipelineFlow";
import { RadarWidget } from "../components/infrastructure/RadarWidget";
import { TerminalLog } from "../components/infrastructure/TerminalLog";
import type { ContainerStatus } from "../types/infrastructure";

function formatUptime(containers: ContainerStatus[]): string {
  const running = containers.filter((c) => c.status === "running");
  if (running.length === 0) return "0%";
  // Use the longest-running container as a proxy for overall uptime.
  // Uptime is displayed as a rounded percentage of a 30-day window (2 592 000 s).
  const maxUptime = Math.max(...running.map((c) => c.uptime_seconds));
  const THIRTY_DAYS_S = 30 * 24 * 60 * 60;
  const pct = Math.min((maxUptime / THIRTY_DAYS_S) * 100, 100);
  return `${pct.toFixed(3)}%`;
}

interface PageHeaderProps {
  serviceCount: number;
  uptime: string;
}

function PageHeader({ serviceCount, uptime }: PageHeaderProps) {
  return (
    <div className="px-6 pt-6 pb-4 flex items-end justify-between border-b border-outline-variant/10">
      <div>
        <p className="font-mono text-[10px] text-outline uppercase tracking-widest mb-1">
          SYSTEM_CORE_LOG_09 // PIPELINE_VISUALIZATION_V1
        </p>
        <h1 className="font-headline text-4xl font-black uppercase tracking-tighter text-on-surface">
          Infrastructure Monitor
        </h1>
      </div>

      <div className="flex gap-6 items-end">
        <div className="text-right">
          <div className="font-mono text-[10px] text-outline uppercase">Uptime</div>
          <div className="font-mono text-lg text-tertiary">{uptime}</div>
        </div>
        <div className="text-right border-l border-outline-variant/20 pl-6">
          <div className="font-mono text-[10px] text-outline uppercase">Services</div>
          <div className="font-mono text-lg text-primary">{serviceCount}</div>
        </div>
      </div>
    </div>
  );
}

export function InfrastructurePage() {
  const { data, error } = useInfraStatus();
  const topology = useTopology();

  const runningContainers = data?.containers.filter((c) => c.status === "running") ?? [];
  const serviceCount = runningContainers.length;
  const uptime = data != null ? formatUptime(data.containers) : "—";

  // Collect the queue names that are explicitly part of the pipeline topology.
  // The pipeline map only shows queues referenced by topology stages (via
  // stage.match.queue). We filter the raw queue list from the API to the same
  // set so that the Queue Depth metric matches what the map displays.
  // Without this filter the metric would count every queue in RabbitMQ,
  // including internal or dead-letter queues that never appear on the map.
  const pipelineQueueNames = useMemo<Set<string>>(() => {
    if (topology == null) return new Set();
    return new Set(
      topology.stages
        .map((s) => s.match.queue)
        .filter((q): q is string => q != null),
    );
  }, [topology]);

  const pipelineQueues = useMemo(
    () =>
      data?.queues != null && pipelineQueueNames.size > 0
        ? data.queues.filter((q) => pipelineQueueNames.has(q.name))
        : data?.queues,
    [data?.queues, pipelineQueueNames],
  );

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader serviceCount={serviceCount} uptime={uptime} />

      {error != null && (
        <div className="mx-6 mt-4 px-4 py-2 bg-error/10 border border-error/30 font-mono text-[10px] text-error uppercase tracking-widest">
          MONITORING_API_ERROR: {error}
        </div>
      )}

      <div className="flex-1 p-6 min-h-0">
        <div className="grid grid-cols-12 grid-rows-[1fr_auto] gap-6 h-full">
          {/* Main pipeline visualization */}
          <PipelineFlow containers={data?.containers} queues={data?.queues} exchanges={data?.exchanges} db={data?.db} />

          {/* Right side panel — min-h-0 lets flex children scroll instead of
              expanding the grid row to fit all log content. */}
          <div className="col-span-12 lg:col-span-3 flex flex-col gap-6 min-h-0 overflow-hidden">
            <RadarWidget />
            <TerminalLog />
          </div>

          {/* Bottom metrics row — queues filtered to pipeline-topology members
              so Queue Depth matches the message counts shown on the map. */}
          <InfraMetricsRow
            db={data?.db}
            queues={pipelineQueues}
            containers={data?.containers}
          />
        </div>
      </div>
    </div>
  );
}
