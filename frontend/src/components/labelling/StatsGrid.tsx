import { ProgressBar } from "../shared/ProgressBar";
import { MaterialIcon } from "../shared/MaterialIcon";
import type { LabellingStats } from "../../types/labelling";

interface StatsGridProps {
  stats: LabellingStats | null;
  onExport: () => void;
}

export function StatsGrid({ stats, onExport }: StatsGridProps) {
  const unlabelledDisplay = stats !== null
    ? stats.unlabelled_count.toLocaleString()
    : "--";

  const progressDisplay = stats !== null
    ? `${stats.progress_percent.toFixed(1)}%`
    : "--";

  const progressValue = stats?.progress_percent ?? 0;

  const classifiedDisplay =
    stats?.classified_count != null
      ? stats.classified_count.toLocaleString()
      : "--";

  return (
    <section className="grid grid-cols-1 md:grid-cols-4 gap-4">
      {/* Card 1: Total unlabelled */}
      <div className="bg-surface-container-low p-6 flex flex-col justify-between relative overflow-hidden">
        <div className="absolute top-0 right-0 p-2 opacity-5 font-mono text-[60px] leading-none pointer-events-none">
          01
        </div>
        <span className="font-mono text-[10px] text-outline uppercase tracking-tighter mb-4">
          _TOTAL_UNLABELLED
        </span>
        <div className="flex items-baseline gap-2">
          <span className="text-4xl font-headline font-bold text-primary">
            {unlabelledDisplay}
          </span>
          <span className="text-xs font-mono text-tertiary">ENTRIES</span>
        </div>
      </div>

      {/* Card 2: Labelling progress */}
      <div className="bg-surface-container-low p-6 flex flex-col justify-between relative overflow-hidden">
        <div className="absolute top-0 right-0 p-2 opacity-5 font-mono text-[60px] leading-none pointer-events-none">
          02
        </div>
        <span className="font-mono text-[10px] text-outline uppercase tracking-tighter mb-4">
          _LABELLING_PROGRESS
        </span>
        <div className="flex items-baseline gap-2 mb-3">
          <span className="text-4xl font-headline font-bold text-primary">
            {progressDisplay}
          </span>
          <span className="text-xs font-mono text-outline">TARGET: 100%</span>
        </div>
        <ProgressBar percent={progressValue} color="bg-primary" />
      </div>

      {/* Card 3: Auto-classified count */}
      <div className="bg-surface-container-low p-6 flex flex-col justify-between relative overflow-hidden">
        <div className="absolute top-0 right-0 p-2 opacity-5 font-mono text-[60px] leading-none pointer-events-none">
          03
        </div>
        <span className="font-mono text-[10px] text-outline uppercase tracking-tighter mb-4">
          _AUTO_CLASSIFIED
        </span>
        <div className="flex items-baseline gap-2">
          <span className="text-4xl font-headline font-bold text-tertiary">
            {classifiedDisplay}
          </span>
          <span className="text-xs font-mono text-outline">ENTRIES</span>
        </div>
      </div>

      {/* Card 4: Download button */}
      <div className="bg-surface-container-low p-6 flex flex-col justify-center gap-4">
        <button
          onClick={onExport}
          className="w-full py-3 px-4 bg-primary text-on-primary font-headline font-bold text-xs uppercase tracking-widest glow-primary transition-all active:scale-95"
        >
          <MaterialIcon name="download" className="text-sm mr-2" />
          DOWNLOAD ALL UNLABELLED
        </button>
        <div className="flex items-center gap-2 px-2">
          <span className="w-1.5 h-1.5 bg-tertiary" />
          <span className="font-mono text-[9px] text-outline uppercase">
            EXPORT: JSONL FORMAT
          </span>
        </div>
      </div>
    </section>
  );
}
