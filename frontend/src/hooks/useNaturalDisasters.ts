import { useCallback, useEffect } from "react";
import type { NaturalDisaster } from "../types/disaster";
import { usePolling } from "./usePolling";

const POLL_INTERVAL_MS = 60_000;

export function useNaturalDisasters(rangeMs: number): {
  events: NaturalDisaster[];
  loading: boolean;
} {
  const buildUrl = useCallback(
    () => {
      const since = new Date(Date.now() - rangeMs).toISOString();
      return `/api/dashboard/natural-disasters?since=${encodeURIComponent(since)}`;
    },
    [rangeMs],
  );

  const { data, loading, error } = usePolling<NaturalDisaster[]>(
    buildUrl,
    POLL_INTERVAL_MS,
  );

  useEffect(() => {
    if (error !== null) {
      console.error("Natural disasters fetch failed:", error);
    }
  }, [error]);

  return {
    events: data ?? [],
    loading,
  };
}
