import { ProgressBar } from "../shared/ProgressBar";
import type { AttributionStats } from "../../types/attribution";

interface AttributionStatsGridProps {
  stats: AttributionStats | null;
}

export function AttributionStatsGrid({ stats }: AttributionStatsGridProps) {
  const totalDisplay = stats !== null ? stats.total_with_entities.toLocaleString() : "--";
  const annotatedDisplay = stats !== null ? stats.annotated_count.toLocaleString() : "--";
  const progressDisplay = stats !== null ? `${stats.progress_percent.toFixed(1)}%` : "--";
  const progressValue = stats?.progress_percent ?? 0;

  return (
    <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* Card 1: Total with entities */}
      <div className="bg-surface-container-low p-6 flex flex-col justify-between relative overflow-hidden">
        <div className="absolute top-0 right-0 p-2 opacity-5 font-mono text-[60px] leading-none pointer-events-none">
          01
        </div>
        <span className="font-mono text-[10px] text-outline uppercase tracking-tighter mb-4">
          _TOTAL_WITH_ENTITIES
        </span>
        <div className="flex items-baseline gap-2">
          <span className="text-4xl font-headline font-bold text-primary">{totalDisplay}</span>
          <span className="text-xs font-mono text-tertiary">ARTICLES</span>
        </div>
      </div>

      {/* Card 2: Annotated count */}
      <div className="bg-surface-container-low p-6 flex flex-col justify-between relative overflow-hidden">
        <div className="absolute top-0 right-0 p-2 opacity-5 font-mono text-[60px] leading-none pointer-events-none">
          02
        </div>
        <span className="font-mono text-[10px] text-outline uppercase tracking-tighter mb-4">
          _ROLES_ANNOTATED
        </span>
        <div className="flex items-baseline gap-2">
          <span className="text-4xl font-headline font-bold text-tertiary">
            {annotatedDisplay}
          </span>
          <span className="text-xs font-mono text-outline">ENTRIES</span>
        </div>
      </div>

      {/* Card 3: Progress */}
      <div className="bg-surface-container-low p-6 flex flex-col justify-between relative overflow-hidden">
        <div className="absolute top-0 right-0 p-2 opacity-5 font-mono text-[60px] leading-none pointer-events-none">
          03
        </div>
        <span className="font-mono text-[10px] text-outline uppercase tracking-tighter mb-4">
          _ANNOTATION_PROGRESS
        </span>
        <div className="flex items-baseline gap-2 mb-3">
          <span className="text-4xl font-headline font-bold text-primary">{progressDisplay}</span>
          <span className="text-xs font-mono text-outline">TARGET: 100%</span>
        </div>
        <ProgressBar percent={progressValue} color="bg-primary" />
      </div>
    </section>
  );
}
