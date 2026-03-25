import { useState, useEffect, useCallback } from "react";
import type {
  LabellingStats,
  ArticlePage,
  FilterStatus,
  SortField,
} from "../types/labelling";

const STATS_POLL_INTERVAL_MS = 30_000;

export function useLabelling(): {
  stats: LabellingStats | null;
  articles: ArticlePage | null;
  loading: boolean;
  error: string | null;
  page: number;
  setPage: (p: number) => void;
  filter: FilterStatus;
  setFilter: (f: FilterStatus) => void;
  sortBy: SortField;
  setSortBy: (s: SortField) => void;
  updateLabels: (articleId: number, labels: string[]) => Promise<boolean>;
  triggerExport: () => void;
} {
  const [stats, setStats] = useState<LabellingStats | null>(null);
  const [articles, setArticles] = useState<ArticlePage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [filter, setFilterRaw] = useState<FilterStatus>("all");
  const [sortBy, setSortBy] = useState<SortField>("date_ingested");

  // When filter changes, reset page to 1 so the user starts from the
  // beginning of the new result set. We wrap setFilter to bundle the
  // page-reset with the filter change — this avoids a brief flash where
  // the old page number is used with the new filter.
  const setFilter = useCallback((f: FilterStatus) => {
    setFilterRaw(f);
    setPage(1);
  }, []);

  // ── Stats polling ───────────────────────────────────────────────
  // Runs once on mount, then every 30 seconds. Independent of articles.
  useEffect(() => {
    let cancelled = false;

    async function fetchStats() {
      try {
        const response = await fetch("/api/labelling/stats");
        if (!response.ok) {
          throw new Error(`Server returned ${response.status}`);
        }
        const json: LabellingStats = await response.json();
        if (!cancelled) {
          setStats(json);
        }
      } catch (err) {
        // Stats errors are non-fatal — we keep the last known stats
        // and let the articles error surface to the user instead.
        if (!cancelled) {
          console.error("Failed to fetch labelling stats:", err);
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
        const response = await fetch(`/api/labelling/articles?${params}`);
        if (!response.ok) {
          throw new Error(`Server returned ${response.status}`);
        }
        const json: ArticlePage = await response.json();
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

  // ── Update labels (optimistic) ─────────────────────────────────
  // PATCH the labels on the server, then update local state so the UI
  // reflects the change immediately without re-fetching the full list.
  const updateLabels = useCallback(
    async (articleId: number, labels: string[]): Promise<boolean> => {
      try {
        const response = await fetch(`/api/labelling/articles/${articleId}/labels`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ labels }),
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
                ? { ...article, manual_labels: labels.length > 0 ? labels : null }
                : article,
            ),
          };
        });

        return true;
      } catch (err) {
        console.error("Failed to update labels:", err);
        return false;
      }
    },
    [],
  );

  const triggerExport = useCallback(() => {
    window.open("/api/labelling/export");
  }, []);

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
    updateLabels,
    triggerExport,
  };
}
