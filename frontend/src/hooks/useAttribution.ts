import { useState, useEffect, useCallback } from "react";
import type {
  AttributionStats,
  AttributionArticlePage,
  AttributionFilter,
  AttributionSort,
} from "../types/attribution";

const STATS_POLL_INTERVAL_MS = 30_000;

export function useAttribution(): {
  stats: AttributionStats | null;
  articles: AttributionArticlePage | null;
  loading: boolean;
  error: string | null;
  page: number;
  setPage: (p: number) => void;
  filter: AttributionFilter;
  setFilter: (f: AttributionFilter) => void;
  sortBy: AttributionSort;
  setSortBy: (s: AttributionSort) => void;
  updateRoles: (articleId: number, roles: Record<string, string>) => Promise<boolean>;
} {
  const [stats, setStats] = useState<AttributionStats | null>(null);
  const [articles, setArticles] = useState<AttributionArticlePage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [filter, setFilterRaw] = useState<AttributionFilter>("all");
  const [sortBy, setSortBy] = useState<AttributionSort>("date_ingested");

  // When filter changes, reset page to 1 so the user starts from the
  // beginning of the new result set. We wrap setFilter to bundle the
  // page-reset with the filter change — this avoids a brief flash where
  // the old page number is used with the new filter.
  const setFilter = useCallback((f: AttributionFilter) => {
    setFilterRaw(f);
    setPage(1);
  }, []);

  // ── Stats polling ───────────────────────────────────────────────
  // Runs once on mount, then every 30 seconds. Independent of articles.
  useEffect(() => {
    let cancelled = false;

    async function fetchStats() {
      try {
        const response = await fetch("/api/attribution/stats");
        if (!response.ok) {
          throw new Error(`Server returned ${response.status}`);
        }
        const json: AttributionStats = await response.json();
        if (!cancelled) {
          setStats(json);
        }
      } catch (err) {
        // Stats errors are non-fatal — we keep the last known stats
        // and let the articles error surface to the user instead.
        if (!cancelled) {
          console.error("Failed to fetch attribution stats:", err);
        }
      }
    }

    fetchStats();
    const intervalId = setInterval(fetchStats, STATS_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, []);

  // ── Articles fetching ───────────────────────────────────────────
  // Re-runs whenever page, filter, or sortBy changes.
  useEffect(() => {
    let cancelled = false;

    async function fetchArticles() {
      setLoading(true);
      try {
        const params = new URLSearchParams({
          page: String(page),
          page_size: "10",
          filter,
          sort_by: sortBy,
          sort_dir: "desc",
        });
        const response = await fetch(`/api/attribution/articles?${params}`);
        if (!response.ok) {
          throw new Error(`Server returned ${response.status}`);
        }
        const json: AttributionArticlePage = await response.json();
        if (!cancelled) {
          setArticles(json);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to fetch articles");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchArticles();

    return () => {
      cancelled = true;
    };
  }, [page, filter, sortBy]);

  // ── Update roles (optimistic) ──────────────────────────────────
  // PATCH the roles on the server, then update local state so the UI
  // reflects the change immediately without re-fetching the full list.
  const updateRoles = useCallback(
    async (articleId: number, roles: Record<string, string>): Promise<boolean> => {
      try {
        const response = await fetch(`/api/attribution/articles/${articleId}/roles`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ roles }),
        });
        if (!response.ok) {
          throw new Error(`Server returned ${response.status}`);
        }

        // Optimistic update: mutate local articles state in place
        setArticles((prev) => {
          if (prev === null) return prev;
          return {
            ...prev,
            articles: prev.articles.map((article) =>
              article.id === articleId
                ? {
                    ...article,
                    manual_entity_roles: Object.keys(roles).length > 0 ? roles : null,
                    entity_roles_labelled_at: new Date().toISOString(),
                  }
                : article,
            ),
          };
        });

        return true;
      } catch (err) {
        console.error("Failed to update entity roles:", err);
        return false;
      }
    },
    [],
  );

  return {
    stats,
    articles,
    loading,
    error,
    page,
    setPage,
    filter,
    setFilter,
    sortBy,
    setSortBy,
    updateRoles,
  };
}
