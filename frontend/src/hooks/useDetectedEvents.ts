import { useCallback } from "react";
import { usePolling } from "./usePolling";
import type { DetectedEvent } from "../types/event";

/**
 * Polls the detected-events endpoint every 60 seconds.
 *
 * Only returns non-historical events (the API already filters those out).
 */
export function useDetectedEvents(rangeMs: number) {
  const buildUrl = useCallback(
    () => {
      const since = new Date(Date.now() - rangeMs).toISOString();
      return `/api/dashboard/events?since=${encodeURIComponent(since)}`;
    },
    [rangeMs],
  );

  const { data, loading } = usePolling<DetectedEvent[]>(
    buildUrl,
    60_000,
  );
  return { events: data ?? [], loading };
}
