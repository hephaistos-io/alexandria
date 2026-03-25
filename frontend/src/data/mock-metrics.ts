import type { DashboardMetrics, IngestionBar } from "../types/pipeline";

export const MOCK_METRICS: DashboardMetrics = {
  totalRecords: 42901232,
  accuracyDelta: "+0.04%",
  activeEndpoints: 12,
  confidenceAvg: 98.42,
  throughput: "1.2GB/s",
  throughputPercent: 65,
};

// Each bar represents one ingestion cycle slot (left to right = oldest to newest).
// totalHeight is the overall bar height as a CSS percentage (0–100).
// signalHeight is the inner "signal" fill as a percentage of totalHeight.
export const MOCK_INGESTION_BARS: IngestionBar[] = [
  { totalHeight: 62, signalHeight: 72 },
  { totalHeight: 78, signalHeight: 68 },
  { totalHeight: 55, signalHeight: 80 },
  { totalHeight: 90, signalHeight: 65 },
  { totalHeight: 47, signalHeight: 75 },
  { totalHeight: 83, signalHeight: 62 },
  { totalHeight: 70, signalHeight: 88 },
  { totalHeight: 95, signalHeight: 70 },
  { totalHeight: 41, signalHeight: 83 },
  { totalHeight: 76, signalHeight: 66 },
];
