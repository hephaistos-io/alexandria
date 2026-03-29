import { useCallback, useEffect } from "react";
import type { ConflictEvent } from "../types/conflict";
import { usePolling } from "./usePolling";

const POLL_INTERVAL_MS = 60_000;

export function useConflictEvents(rangeMs: number): {
  events: ConflictEvent[];
  loading: boolean;
} {
  const buildUrl = useCallback(
    () => {
      const since = new Date(Date.now() - rangeMs).toISOString();
      return `/api/dashboard/conflict-events?since=${encodeURIComponent(since)}`;
    },
    [rangeMs],
  );

  const { data, loading, error } = usePolling<ConflictEvent[]>(
    buildUrl,
    POLL_INTERVAL_MS,
  );

  // Log errors once when the error state changes, not on every render.
  useEffect(() => {
    if (error !== null) {
      console.error("Conflict events fetch failed:", error);
    }
  }, [error]);

  return {
    events: data ?? [],
    loading,
  };
}
