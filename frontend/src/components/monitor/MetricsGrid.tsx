import { MOCK_METRICS } from "../../data/mock-metrics";
import { MaterialIcon } from "../shared/MaterialIcon";
import { MetricCard } from "../shared/MetricCard";

export function MetricsGrid() {
  function handleDownload() {
    // Placeholder — wire up to real export when available
    console.log("Downloading report...");
  }

  return (
    <div className="col-span-12 lg:col-span-3 flex flex-col gap-6">
      <MetricCard
        label="TOTAL_RECORDS_INGESTED"
        value={MOCK_METRICS.totalRecords.toLocaleString()}
        accentColor="border-primary"
      />

      <MetricCard
        label="ACCURACY_DELTA (24H)"
        value={MOCK_METRICS.accuracyDelta}
        accentColor="border-tertiary"
        valueClassName="text-2xl font-headline font-black text-tertiary"
      />

      <MetricCard
        label="ACTIVE_API_ENDPOINTS"
        value={String(MOCK_METRICS.activeEndpoints)}
        accentColor="border-outline-variant"
      />

      {/* Interactive download card — distinct styling from MetricCard */}
      <div
        className="bg-surface-container-high p-4 flex items-center justify-between group cursor-pointer hover:bg-primary transition-colors"
        onClick={handleDownload}
      >
        <span className="font-mono text-[10px] text-on-surface group-hover:text-on-primary">
          _DOWNLOAD_REPORT
        </span>
        <MaterialIcon
          name="download"
          className="text-primary group-hover:text-on-primary transition-colors"
        />
      </div>
    </div>
  );
}
