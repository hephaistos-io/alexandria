import { useEffect } from "react";
import type { ConflictEvent } from "../types/conflict";
import { usePolling } from "./usePolling";

const POLL_INTERVAL_MS = 60_000;

export function useConflictEvents(): {
  events: ConflictEvent[];
  loading: boolean;
} {
  const { data, loading, error } = usePolling<ConflictEvent[]>(
    `/api/dashboard/conflict-events?limit=200`,
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
