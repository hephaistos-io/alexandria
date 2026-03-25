import { useState } from "react";
import { useArchive } from "../hooks/useArchive";
import { ArchiveCard } from "../components/archive/ArchiveCard";
import { Pagination } from "../components/shared/Pagination";
import { MaterialIcon } from "../components/shared/MaterialIcon";

// Nine skeleton cards that pulse while data is loading.
// Using a fixed count of 9 matches the page_size so the layout doesn't jump.
function SkeletonGrid() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {Array.from({ length: 9 }).map((_, i) => (
        <div
          key={i}
          className="bg-surface-container-low flex flex-col animate-pulse"
        >
          {/* Header bar skeleton */}
          <div className="bg-surface-container-highest px-4 py-2 flex justify-between items-center border-b border-outline-variant/10">
            <div className="h-3 w-24 bg-outline-variant/20" />
            <div className="h-3 w-16 bg-outline-variant/20" />
          </div>
          {/* Body skeleton */}
          <div className="p-5 flex-1 flex flex-col gap-3">
            <div className="h-4 w-full bg-outline-variant/20" />
            <div className="h-4 w-4/5 bg-outline-variant/20" />
            <div className="h-3 w-full bg-outline-variant/10 mt-2" />
            <div className="h-3 w-3/4 bg-outline-variant/10" />
            <div className="mt-auto flex gap-2">
              <div className="h-4 w-16 bg-outline-variant/15" />
              <div className="h-4 w-20 bg-outline-variant/15" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function ArchivePage() {
  const {
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
  } = useArchive();

  const [reparsingAll, setReparsingAll] = useState(false);
  const [reparseResult, setReparseResult] = useState<string | null>(null);

  async function handleReparseAll() {
    const confirmed = window.confirm(
      "WARNING: This will DELETE all articles from the database and re-fetch them from their source URLs. Articles will temporarily disappear and gradually re-appear as scrapers process them. Continue?"
    );
    if (!confirmed) return;

    setReparsingAll(true);
    setReparseResult(null);
    try {
      const response = await fetch("/api/archive/articles/reparse-all", {
        method: "POST",
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `HTTP ${response.status}`);
      }
      const data = await response.json();
      setReparseResult(`${data.count} articles deleted and queued for re-scrape`);
      refresh();
    } catch (err) {
      setReparseResult(`Failed: ${err instanceof Error ? err.message : "unknown error"}`);
    } finally {
      setReparsingAll(false);
    }
  }

  // Toggle between ascending and descending date sort
  function toggleSort() {
    setSortDir(sortDir === "desc" ? "asc" : "desc");
  }

  const articleList = articles?.articles ?? [];
  const total = articles?.total ?? 0;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Page header */}
      <div className="px-6 pt-6 pb-4 flex items-end justify-between border-b border-outline-variant/10">
        <div>
          <p className="font-mono text-[10px] text-outline uppercase tracking-widest mb-1">
            SYSTEM_CORE_LOG_11 // SIGNAL_ARCHIVE_V1
          </p>
          <h1 className="font-headline text-4xl font-black uppercase tracking-tighter text-on-surface">
            Signal Archive
          </h1>
        </div>
      </div>

      {/* Error banner */}
      {error !== null && (
        <div className="mx-6 mt-4 px-4 py-2 bg-error/10 border border-error/30 font-mono text-[10px] text-error uppercase tracking-widest">
          ARCHIVE_API_ERROR: {error}
        </div>
      )}

      {/* Reparse result banner */}
      {reparseResult !== null && (
        <div className="mx-6 mt-4 px-4 py-2 bg-tertiary/10 border border-tertiary/30 font-mono text-[10px] text-tertiary uppercase tracking-widest flex items-center justify-between">
          <span>{reparseResult}</span>
          <button onClick={() => setReparseResult(null)} className="text-tertiary hover:text-on-surface ml-4">
            <MaterialIcon name="close" className="text-sm" />
          </button>
        </div>
      )}

      {/* Scrollable content */}
      <div className="flex-1 p-6 overflow-y-auto space-y-6">
        {/* Search + Sort bar */}
        <section className="max-w-7xl mx-auto w-full">
          <div className="bg-surface-container-low p-1 border-b border-outline-variant/20 flex flex-col md:flex-row items-stretch md:items-center gap-4">
            {/* Search input */}
            <div className="flex-1 relative flex items-center group">
              <MaterialIcon
                name="search"
                className="absolute left-4 text-outline group-focus-within:text-primary transition-colors"
              />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="SEARCH_ARCHIVE // INPUT_QUERY..."
                className="w-full bg-surface-container-highest border-none focus:ring-0 text-on-surface font-mono text-xs pl-12 pr-16 py-4 placeholder:text-outline/40"
              />
              <div className="absolute right-4 font-mono text-[8px] text-outline/30 select-none">
                CMD+F
              </div>
            </div>

            {/* Sort control */}
            <div className="flex items-center bg-surface-container-highest px-4 border-l border-outline-variant/20">
              <button
                onClick={toggleSort}
                className="font-mono text-[10px] text-outline mr-4 uppercase hover:text-primary transition-colors"
                aria-label="Toggle sort direction"
              >
                Sort: DATE_{sortDir.toUpperCase() === "DESC" ? "DESC" : "ASC"}
              </button>
              <button
                onClick={toggleSort}
                className="p-2 text-outline hover:text-primary transition-colors"
                aria-label="Filter"
              >
                <MaterialIcon name="filter_list" />
              </button>
            </div>

            {/* Reclassify all */}
            <button
              onClick={handleReparseAll}
              disabled={reparsingAll}
              className="flex items-center gap-2 bg-surface-container-highest px-4 py-3 border-l border-outline-variant/20 font-mono text-[10px] text-outline uppercase hover:text-primary transition-colors disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
            >
              <MaterialIcon name="replay" className={`text-sm ${reparsingAll ? "animate-spin" : ""}`} />
              {reparsingAll ? "QUEUING..." : "RECLASSIFY_ALL"}
            </button>
          </div>
        </section>

        {/* Card grid */}
        <section className="max-w-7xl mx-auto w-full">
          {loading ? (
            <SkeletonGrid />
          ) : articleList.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 gap-4">
              <MaterialIcon name="inventory_2" className="text-4xl text-outline/30" />
              <p className="font-mono text-[10px] text-outline uppercase tracking-widest">
                NO_SIGNALS_FOUND // ARCHIVE_EMPTY
              </p>
              {search && (
                <p className="font-mono text-[9px] text-outline/50">
                  QUERY: "{search}" — NO MATCHES
                </p>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {articleList.map((article) => (
                <ArchiveCard key={article.id} article={article} />
              ))}
            </div>
          )}
        </section>

        {/* Pagination — only shown when there is data */}
        {!loading && total > 0 && (
          <section className="max-w-7xl mx-auto w-full pb-8">
            <Pagination
              page={page}
              totalPages={Math.max(1, Math.ceil(total / 9))}
              onPageChange={setPage}
              showPageNumbers
              totalEntries={total}
              pageSize={9}
            />
          </section>
        )}
      </div>
    </div>
  );
}
