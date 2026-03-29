import { useCallback, useEffect } from "react";
import type { DashboardArticle } from "../types/dashboard";
import { usePolling } from "./usePolling";

const POLL_INTERVAL_MS = 60_000;

export function useDashboardArticles(rangeMs: number): {
  articles: DashboardArticle[];
  loading: boolean;
} {
  // URL factory: recomputed on every poll tick so the `since` timestamp
  // stays fresh relative to Date.now() instead of drifting.
  const buildUrl = useCallback(
    () => {
      const since = new Date(Date.now() - rangeMs).toISOString();
      return `/api/dashboard/articles?since=${encodeURIComponent(since)}`;
    },
    [rangeMs],
  );

  const { data, loading, error } = usePolling<DashboardArticle[]>(
    buildUrl,
    POLL_INTERVAL_MS,
  );

  // Log errors once when the error state changes, not on every render.
  useEffect(() => {
    if (error !== null) {
      console.error("Dashboard articles fetch failed:", error);
    }
  }, [error]);

  return {
    articles: data ?? [],
    loading,
  };
}
