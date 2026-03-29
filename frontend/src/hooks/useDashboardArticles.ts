import { useEffect, useMemo } from "react";
import type { DashboardArticle } from "../types/dashboard";
import { usePolling } from "./usePolling";

const POLL_INTERVAL_MS = 60_000;

export function useDashboardArticles(rangeMs: number): {
  articles: DashboardArticle[];
  loading: boolean;
} {
  const since = useMemo(
    () => new Date(Date.now() - rangeMs).toISOString(),
    [rangeMs],
  );

  const { data, loading, error } = usePolling<DashboardArticle[]>(
    `/api/dashboard/articles?since=${encodeURIComponent(since)}`,
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
