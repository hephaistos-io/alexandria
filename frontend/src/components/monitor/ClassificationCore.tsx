import { MOCK_METRICS } from "../../data/mock-metrics";
import { MaterialIcon } from "../shared/MaterialIcon";
import { ProgressBar } from "../shared/ProgressBar";

export function ClassificationCore() {
  return (
    <div className="bg-surface-container-low p-6 col-span-12 lg:col-span-4 flex flex-col gap-6 relative overflow-hidden">
      {/* Decorative background icon */}
      <div className="absolute -right-4 -top-4 opacity-5 pointer-events-none">
        <MaterialIcon name="memory" className="text-8xl" />
      </div>

      <h3 className="font-headline text-sm font-bold text-on-surface uppercase tracking-widest">
        Classification Core
      </h3>

      {/* Confidence */}
      <div className="flex flex-col gap-2 relative z-10">
        <p className="font-mono text-[10px] text-outline">CONFIDENCE_AVG</p>
        <p className="font-headline text-3xl font-black text-on-surface">
          {MOCK_METRICS.confidenceAvg}%
        </p>
        <ProgressBar percent={MOCK_METRICS.confidenceAvg} color="bg-tertiary" />
      </div>

      {/* Throughput */}
      <div className="flex flex-col gap-2 relative z-10">
        <p className="font-mono text-[10px] text-outline">THROUGHPUT</p>
        <p className="font-headline text-xl font-bold text-on-surface">
          {MOCK_METRICS.throughput}
        </p>
        <ProgressBar percent={MOCK_METRICS.throughputPercent} />
      </div>

      {/* Status badge */}
      <div className="mt-auto pt-6 border-t border-outline-variant/15 flex items-center gap-4">
        <div className="w-10 h-10 border border-outline-variant/20 flex items-center justify-center shrink-0">
          <MaterialIcon name="check_circle" className="text-tertiary" />
        </div>
        <div>
          <p className="font-headline font-bold text-xs uppercase text-on-surface">
            CORE_OPTIMIZED
          </p>
          <p className="font-mono text-[10px] text-outline">Last check: 0.2ms ago</p>
        </div>
      </div>
    </div>
  );
}
