import { useState, useEffect } from "react";
import type { ArchivePage } from "../types/archive";

export function useArchive(): {
  articles: ArchivePage | null;
  loading: boolean;
  error: string | null;
  page: number;
  setPage: (p: number) => void;
  search: string;
  setSearch: (s: string) => void;
  sortDir: "asc" | "desc";
  setSortDir: (d: "asc" | "desc") => void;
  refresh: () => void;
} {
  const [page, setPage] = useState(1);
  const [search, setSearchRaw] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [articles, setArticles] = useState<ArchivePage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // Debounce the search input by 300ms. When the user types, `search` updates
  // immediately (so the input field feels responsive), but `debouncedSearch`
  // only updates after the user pauses for 300ms. The fetch effect depends on
  // `debouncedSearch`, so the API is not called on every keystroke.
  useEffect(() => {
    const timerId = setTimeout(() => {
      setDebouncedSearch(search);
    }, 300);

    // The cleanup function runs before the next effect, cancelling the
    // pending timer if the user types again before 300ms elapses.
    return () => clearTimeout(timerId);
  }, [search]);

  // Wrap setSearch so it also resets the page to 1. Otherwise the user could
  // be on page 5, type a new query with fewer results, and see an empty page.
  function setSearch(s: string) {
    setSearchRaw(s);
    setPage(1);
  }

  // Fetch articles whenever the effective search, page, or sort direction
  // changes. Note: this depends on `debouncedSearch`, not `search`.
  useEffect(() => {
    let cancelled = false;

    async function fetchArticles() {
      setLoading(true);
      try {
        const params = new URLSearchParams({
          page: String(page),
          page_size: "9",
          search: debouncedSearch,
          sort_dir: sortDir,
        });
        const response = await fetch(`/api/archive/articles?${params}`);
        if (!response.ok) {
          throw new Error(`Server returned ${response.status}`);
        }
        const json: ArchivePage = await response.json();
        if (!cancelled) {
          setArticles(json);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to fetch archive");
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
  }, [page, debouncedSearch, sortDir, refreshKey]);

  function refresh() {
    setRefreshKey((k) => k + 1);
  }

  return {
    articles,
    loading,
    error,
    page,
    setPage,
    search,
    setSearch,
    sortDir,
    setSortDir,
    refresh,
  };
}
