import type { PipelineTopology } from "../config/pipelineTopology";
import { usePolling } from "./usePolling";

const POLL_INTERVAL_MS = 30000;

// Returns the topology directly (or null before the first successful fetch).
// Errors are silently swallowed — the graph stays stable and will retry on
// the next interval tick, matching the original behaviour.
export function useTopology(): PipelineTopology | null {
  const { data } = usePolling<PipelineTopology>("/api/topology", POLL_INTERVAL_MS);
  return data;
}
