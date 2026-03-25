import type { InfraStatus } from "../types/infrastructure";
import { usePolling } from "./usePolling";

const POLL_INTERVAL_MS = 5000;

export function useInfraStatus(): {
  data: InfraStatus | null;
  loading: boolean;
  error: string | null;
} {
  return usePolling<InfraStatus>("/api/status", POLL_INTERVAL_MS);
}
