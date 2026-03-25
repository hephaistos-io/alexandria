import { useEffect } from "react";
import type { DashboardArticle } from "../types/dashboard";
import { usePolling } from "./usePolling";

const POLL_INTERVAL_MS = 60_000;

export function useDashboardArticles(): {
  articles: DashboardArticle[];
  loading: boolean;
} {
  const { data, loading, error } = usePolling<DashboardArticle[]>(
    "/api/dashboard/articles?limit=20",
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
