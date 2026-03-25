import { MOCK_INGESTION_BARS } from "../../data/mock-metrics";

export function IngestionChart() {
  return (
    <div className="bg-surface-container-low p-6 col-span-12 lg:col-span-8 relative">
      <div className="absolute top-0 right-0 p-2 font-mono text-[10px] text-outline/40">
        REF_ID: GRPH_001
      </div>

      {/* Header row */}
      <div className="flex justify-between items-center mb-4 border-b border-outline-variant/15 pb-4">
        <h3 className="font-headline text-sm font-bold text-on-surface uppercase tracking-widest">
          Ingestion Rate / Magnitude
        </h3>
        <div className="flex gap-4 font-mono text-[10px] text-on-surface">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 bg-primary inline-block" />
            SIGNAL
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 bg-tertiary inline-block" />
            NOISE
          </span>
        </div>
      </div>

      {/* Bar chart */}
      <div className="h-64 flex items-end gap-1 mt-4">
        {MOCK_INGESTION_BARS.map((bar, index) => {
          return (
            <div
              key={index}
              className="flex-1 relative group cursor-crosshair"
              style={{ height: `${bar.totalHeight}%` }}
            >
              {/* Background (noise) fill — full bar height */}
              <div className="absolute inset-0 w-full bg-primary/10 group-hover:bg-primary/20 transition-all duration-300" />

              {/* Signal fill — bottom portion */}
              <div
                className="absolute bottom-0 w-full bg-primary group-hover:bg-primary/80 transition-all duration-300"
                style={{ height: `${bar.signalHeight}%` }}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
