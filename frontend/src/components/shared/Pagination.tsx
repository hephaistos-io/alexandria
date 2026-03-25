import { MaterialIcon } from "./MaterialIcon";

interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  /** When true, renders numbered page buttons with ellipsis between them. */
  showPageNumbers?: boolean;
  /** Total entry count used to render the "SHOWING x-y/z ENTRIES" label.
   *  Pass undefined to omit the entry range display. */
  totalEntries?: number;
  /** Number of entries per page, required when totalEntries is provided. */
  pageSize?: number;
}

// Compute a compact list of page numbers to show, with ellipsis gaps
// represented as null. For example with 10 total pages on page 5:
//   [1, null, 4, 5, 6, null, 10]
// We always show the first and last page, the current page, and one
// neighbour on each side.
function buildPageNumbers(current: number, total: number): (number | null)[] {
  if (total <= 5) {
    // Small total: just show all pages, no ellipsis needed.
    return Array.from({ length: total }, (_, i) => i + 1);
  }

  const pages: (number | null)[] = [];
  const neighbours = new Set([1, total, current, current - 1, current + 1]);

  // Build a sorted unique list of page numbers in range [1, total]
  const validPages = [...neighbours]
    .filter((p) => p >= 1 && p <= total)
    .sort((a, b) => a - b);

  for (let i = 0; i < validPages.length; i++) {
    pages.push(validPages[i]);
    // Insert ellipsis if the gap to the next page is more than 1
    if (i < validPages.length - 1 && validPages[i + 1] - validPages[i] > 1) {
      pages.push(null);
    }
  }

  return pages;
}

export function Pagination({
  page,
  totalPages,
  onPageChange,
  showPageNumbers = false,
  totalEntries,
  pageSize,
}: PaginationProps) {
  const isFirstPage = page <= 1;
  const isLastPage = page >= totalPages;

  // Compute range label only when caller supplies both totalEntries and pageSize.
  const showEntryRange = totalEntries !== undefined && pageSize !== undefined;
  const rangeStart = showEntryRange && totalEntries > 0 ? pageSize * (page - 1) + 1 : 0;
  const rangeEnd = showEntryRange ? Math.min(pageSize * page, totalEntries) : 0;

  if (showPageNumbers) {
    // ── Full pagination bar with numbered buttons (used by Archive) ───────────
    const pageNumbers = buildPageNumbers(page, totalPages);

    return (
      <div className="flex flex-col sm:flex-row items-center justify-between gap-6 border-t border-outline-variant/20 pt-8">
        {/* Entry count */}
        <div className="flex items-center gap-2">
          {showEntryRange ? (
            <span className="font-mono text-[10px] text-outline uppercase">
              Showing: {rangeStart}-{rangeEnd} OF {totalEntries} ENTRIES
            </span>
          ) : (
            <span className="font-mono text-[10px] text-outline uppercase">
              PAGE_INDEX: {String(page).padStart(3, "0")}/{String(totalPages).padStart(3, "0")}
            </span>
          )}
        </div>

        {/* Page controls */}
        <div className="flex items-center bg-surface-container-low">
          {/* Previous button */}
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={isFirstPage}
            className={`px-4 py-3 border border-outline-variant/20 flex items-center gap-1 group transition-colors
              ${isFirstPage ? "opacity-30 cursor-not-allowed" : "hover:bg-surface-container-highest"}`}
            aria-label="Previous page"
          >
            <MaterialIcon
              name="chevron_left"
              className={`text-sm transition-transform ${!isFirstPage ? "group-hover:-translate-x-1" : ""}`}
            />
            <span className="font-mono text-[10px] tracking-widest uppercase">PREV_BLOCK</span>
          </button>

          {/* Page number buttons */}
          <div className="flex border-y border-outline-variant/20">
            {pageNumbers.map((p, i) =>
              p === null ? (
                <div
                  key={`ellipsis-${i}`}
                  className="w-12 h-10 flex items-center justify-center font-mono text-[10px] text-outline/30"
                >
                  ...
                </div>
              ) : (
                <button
                  key={p}
                  onClick={() => onPageChange(p)}
                  className={`w-12 h-10 flex items-center justify-center font-mono text-[10px] transition-colors
                    ${
                      p === page
                        ? "bg-primary text-on-primary font-bold"
                        : "hover:bg-surface-container-highest text-outline"
                    }`}
                  aria-label={`Page ${p}`}
                  aria-current={p === page ? "page" : undefined}
                >
                  {String(p).padStart(2, "0")}
                </button>
              ),
            )}
          </div>

          {/* Next button */}
          <button
            onClick={() => onPageChange(page + 1)}
            disabled={isLastPage}
            className={`px-4 py-3 border border-outline-variant/20 flex items-center gap-1 group transition-colors
              ${isLastPage ? "opacity-30 cursor-not-allowed" : "hover:bg-surface-container-highest"}`}
            aria-label="Next page"
          >
            <span className="font-mono text-[10px] tracking-widest uppercase">NEXT_BLOCK</span>
            <MaterialIcon
              name="chevron_right"
              className={`text-sm transition-transform ${!isLastPage ? "group-hover:translate-x-1" : ""}`}
            />
          </button>
        </div>
      </div>
    );
  }

  // ── Compact pagination bar with simple PREV/NEXT buttons (Labelling/Attribution) ──
  return (
    <div className="flex justify-between items-center p-4 bg-surface-container-lowest font-mono text-[10px] text-outline">
      <div className="flex items-center gap-4">
        <span>
          PAGE_INDEX: {String(page).padStart(3, "0")}/{String(totalPages).padStart(3, "0")}
        </span>
        {showEntryRange && (
          <span>
            SHOWING: {rangeStart}-{rangeEnd}/{totalEntries.toLocaleString()} ENTRIES
          </span>
        )}
      </div>
      <div className="flex gap-2">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={isFirstPage}
          className={`px-3 py-1 bg-surface-container-high transition-colors ${
            isFirstPage ? "opacity-30 cursor-not-allowed" : "hover:text-on-surface"
          }`}
          aria-label="Previous page"
        >
          PREV
        </button>
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={isLastPage}
          className={`px-3 py-1 bg-surface-container-high transition-colors ${
            isLastPage ? "opacity-30 cursor-not-allowed" : "hover:text-on-surface"
          }`}
          aria-label="Next page"
        >
          NEXT
        </button>
      </div>
    </div>
  );
}
