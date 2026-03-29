import { Link } from "react-router";
import { ArticleCard } from "./ArticleCard";
import type { DashboardArticle } from "../../types/dashboard";
import type { DetectedEventDetail, EventArticle } from "../../types/event";
import type { GeoAnchor } from "../../types/pipeline";
import { adaptEventArticle } from "../../utils/adaptEventArticle";
import { formatDate } from "../../utils/formatDate";

interface TimeRangeOption {
  key: string;
  label: string;
  ms: number;
}

interface ScrapedFeedsPanelProps {
  articles: DashboardArticle[];
  loading: boolean;
  selectedAnchor?: GeoAnchor | null;
  onArticleClick?: (articleId: number) => void;
  onDismissSelection?: () => void;
  timeRange?: string;
  timeRanges?: readonly TimeRangeOption[];
  onTimeRangeChange?: (key: string) => void;
  focusedEventId?: number | null;
  eventDetail?: DetectedEventDetail | null;
  eventDetailLoading?: boolean;
  onClearFocus?: () => void;
}

// Status badge colors follow the event lifecycle: yellow for emerging threats,
// green for active, blue for cooling down, gray for archived history.
const STATUS_STYLES: Record<DetectedEventDetail["status"], string> = {
  emerging: "border-yellow-400/50 text-yellow-400",
  active: "border-green-400/50 text-green-400",
  cooling: "border-blue-400/50 text-blue-400",
  historical: "border-outline/50 text-outline",
};

export function ScrapedFeedsPanel({
  articles,
  loading,
  selectedAnchor,
  onArticleClick,
  onDismissSelection,
  timeRange,
  timeRanges,
  onTimeRangeChange,
  focusedEventId,
  eventDetail,
  eventDetailLoading,
  onClearFocus,
}: ScrapedFeedsPanelProps) {
  // ── Event focus mode ────────────────────────────────────────────────────────
  // When an event marker is clicked we replace the entire panel content with a
  // focused view of that event's related articles and conflicts.
  if (focusedEventId !== null && focusedEventId !== undefined) {
    return (
      <div className="w-96 shrink-0 bg-surface-container-low flex flex-col border-l border-outline-variant/10">
        {/* Focus mode header */}
        <div className="p-4 border-b border-outline-variant/10 bg-surface-container shrink-0">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="inline-block w-1 h-1 bg-purple-400 shadow-[0_0_6px_#c084fc]" />
              <h2 className="font-headline text-lg font-bold text-on-surface">
                EVENT_FOCUS
              </h2>
            </div>
            <button
              onClick={onClearFocus}
              className="font-mono text-[10px] text-outline/50 hover:text-on-surface transition-colors px-1"
              aria-label="Clear focus"
            >
              ×
            </button>
          </div>
          <span className="font-mono text-[9px] text-purple-400/70 uppercase tracking-widest">
            EVT_{focusedEventId.toString(16).toUpperCase().padStart(5, "0")}
          </span>
        </div>

        {/* Loading state */}
        {eventDetailLoading && (
          <div className="flex items-center justify-center py-12">
            <span className="font-mono text-[10px] text-outline uppercase tracking-widest">
              LOADING_EVENT...
            </span>
          </div>
        )}

        {/* No detail loaded (fetch failed or still null after load) */}
        {!eventDetailLoading && !eventDetail && (
          <div className="flex-1 flex items-center justify-center">
            <span className="font-mono text-[10px] text-outline uppercase tracking-widest">
              EVENT_NOT_FOUND
            </span>
          </div>
        )}

        {/* Loaded event detail */}
        {!eventDetailLoading && eventDetail && (
          <div className="flex-1 overflow-y-auto">
            {/* Event info card */}
            <div className="mx-3 mt-3 mb-2 p-3 border-l-2 border-purple-400 bg-purple-400/[0.06]">
              <div className="flex items-start justify-between mb-2">
                <span
                  className={`font-mono text-[9px] px-1.5 py-0.5 border uppercase tracking-wider ${STATUS_STYLES[eventDetail.status]}`}
                >
                  {eventDetail.status}
                </span>
                <span className="font-mono text-[10px] text-purple-400/70">
                  HEAT: {eventDetail.heat.toFixed(1)}
                </span>
              </div>

              <h3 className="font-headline text-sm font-bold text-on-surface mb-2 leading-snug">
                {eventDetail.title}
              </h3>

              <div className="grid grid-cols-2 gap-x-2 gap-y-1 mt-3">
                <div>
                  <span className="block font-mono text-[8px] text-outline/50 uppercase tracking-widest">
                    FIRST_SEEN
                  </span>
                  <span className="font-mono text-[9px] text-on-surface-variant">
                    {formatDate(eventDetail.first_seen)}
                  </span>
                </div>
                <div>
                  <span className="block font-mono text-[8px] text-outline/50 uppercase tracking-widest">
                    LAST_SEEN
                  </span>
                  <span className="font-mono text-[9px] text-on-surface-variant">
                    {formatDate(eventDetail.last_seen)}
                  </span>
                </div>
              </div>
            </div>

            {/* Related conflicts count */}
            {eventDetail.conflicts.length > 0 && (
              <div className="px-3 py-2 border-b border-outline-variant/10">
                <div className="flex items-center gap-2 mb-2">
                  <span className="font-mono text-[9px] text-outline/50 uppercase tracking-widest">
                    CONFLICT_EVENTS
                  </span>
                  <span className="font-mono text-[9px] text-purple-400">
                    [{eventDetail.conflicts.length}]
                  </span>
                </div>
                <div className="space-y-1">
                  {eventDetail.conflicts.map((c) => (
                    <div
                      key={c.id}
                      className="flex justify-between items-start gap-2"
                    >
                      <span className="font-mono text-[9px] text-on-surface-variant leading-snug line-clamp-1 flex-1">
                        {c.title}
                      </span>
                      <span className="font-mono text-[9px] text-outline/50 shrink-0">
                        {c.place_desc || "—"}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Related articles section label */}
            <div className="px-3 pt-3 pb-1 flex items-center gap-2">
              <span className="font-mono text-[9px] text-outline/50 uppercase tracking-widest">
                RELATED_ARTICLES
              </span>
              <span className="font-mono text-[9px] text-purple-400">
                [{eventDetail.articles.length}]
              </span>
            </div>

            {/* Article list reusing ArticleCard — each EventArticle is adapted
                to DashboardArticle shape so the card renders identically */}
            <div className="px-4 py-1 space-y-1">
              {eventDetail.articles.length === 0 && (
                <span className="font-mono text-[9px] text-outline/50">
                  NO_ARTICLES
                </span>
              )}
              {eventDetail.articles.map((a) => (
                <ArticleCard key={a.id} article={adaptEventArticle(a)} />
              ))}
            </div>
          </div>
        )}

        {/* Footer with clear focus action */}
        <div className="p-3 bg-surface-container-lowest border-t border-outline-variant/10 shrink-0">
          <button
            onClick={onClearFocus}
            className="font-mono text-[10px] text-purple-400/70 hover:text-purple-400 transition-colors uppercase tracking-widest"
          >
            &gt; CLEAR_FOCUS
          </button>
        </div>
      </div>
    );
  }

  // ── Normal mode ─────────────────────────────────────────────────────────────
  return (
    <div className="w-96 shrink-0 bg-surface-container-low flex flex-col border-l border-outline-variant/10">
      {/* Panel header */}
      <div className="p-4 border-b border-outline-variant/10 bg-surface-container shrink-0">
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-headline text-lg font-bold text-on-surface">
            SCRAPED_FEEDS
          </h2>
          {/* Live update badge — the small square before the text is a
              decorative inline-block element styled as a tertiary accent */}
          <div className="flex items-center">
            <span className="inline-block w-1 h-1 bg-tertiary mr-1" />
            <span className="font-mono text-[9px] text-tertiary">
              LIVE_UPDATE
            </span>
          </div>
        </div>

        {/* Filter tag pills + time range selector */}
        <div className="flex items-center gap-2">
          <span className="bg-surface-container-high px-2 py-1 font-mono text-[9px] text-outline">
            GLOBAL_NET
          </span>
          <span className="bg-surface-container-high px-2 py-1 font-mono text-[9px] text-outline">
            ENCRYPTED
          </span>
          {timeRanges && onTimeRangeChange && (
            <div className="ml-auto flex items-center gap-1">
              {timeRanges.map((r) => (
                <button
                  key={r.key}
                  onClick={() => onTimeRangeChange(r.key)}
                  className={`px-2 py-1 font-mono text-[9px] uppercase tracking-wider border transition-colors ${
                    timeRange === r.key
                      ? "border-primary/60 text-primary bg-primary/10"
                      : "border-outline-variant/30 text-outline hover:text-on-surface hover:border-outline-variant/60"
                  }`}
                >
                  {r.key.toUpperCase()}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Selected anchor detail card — shown when a map marker is clicked */}
      {selectedAnchor && (
        <div className="shrink-0 border-b border-outline-variant/10 animate-[slideDown_150ms_ease-out]">
          {/* Section label */}
          <div className="px-4 pt-3 pb-1.5 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 bg-primary shadow-[0_0_6px_var(--color-primary)]" />
              <span className="font-mono text-[9px] text-primary uppercase tracking-widest">
                SELECTED_INTERCEPT
              </span>
            </div>
            <button
              onClick={onDismissSelection}
              className="font-mono text-[10px] text-outline/50 hover:text-on-surface transition-colors px-1"
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>

          {/* Card body with left accent border and glow background */}
          <div className="mx-3 mb-3 p-3 border-l-2 border-primary bg-primary/[0.06] shadow-[inset_0_0_20px_rgba(118,169,250,0.04)]">
            {/* Category + date row */}
            <div className="flex justify-between items-start mb-2">
              <span className="font-mono text-[9px] text-tertiary uppercase tracking-wider">
                {selectedAnchor.category}
              </span>
              <span className="font-mono text-[10px] text-outline">
                {selectedAnchor.date}
              </span>
            </div>

            {/* Location */}
            <div className="font-mono text-[9px] text-primary/60 uppercase tracking-widest mb-1">
              {selectedAnchor.city}
            </div>

            {/* Article title — no line-clamp so full title is visible */}
            <h4 className="font-headline text-sm font-bold text-on-surface mb-2">
              {selectedAnchor.label}
            </h4>

            {/* Summary — more lines visible than feed cards */}
            <p className="text-xs text-on-surface-variant leading-relaxed mb-3 line-clamp-4">
              {selectedAnchor.summary}
            </p>

            {/* Topic labels */}
            {selectedAnchor.labels.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-3">
                {selectedAnchor.labels.map((lbl) => (
                  <span
                    key={lbl}
                    className="px-1.5 py-0.5 text-[8px] font-mono uppercase border border-primary/30 text-primary"
                  >
                    {lbl}
                  </span>
                ))}
              </div>
            )}

            {/* Footer */}
            <div className="flex justify-between items-center">
              <span className="font-mono text-[9px] text-outline/50">
                SRC: {selectedAnchor.source}
              </span>
              <Link
                to={`/archive/${selectedAnchor.id}`}
                className="font-mono text-[9px] text-primary hover:text-tertiary transition-colors uppercase tracking-wider"
              >
                OPEN_ARTICLE →
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Scrollable article list — flex-1 ensures it fills remaining height
          and overflow-y-auto enables independent scrolling */}
      <div className="flex-1 overflow-y-auto px-4 py-2 space-y-1">
        {loading && (
          <div className="flex items-center justify-center py-12">
            <span className="font-mono text-[10px] text-outline uppercase tracking-widest">
              LOADING_FEEDS...
            </span>
          </div>
        )}
        {!loading && articles.length === 0 && (
          <div className="flex items-center justify-center py-12">
            <span className="font-mono text-[10px] text-outline uppercase tracking-widest">
              NO_FEEDS_AVAILABLE
            </span>
          </div>
        )}
        {!loading &&
          articles.map((article) => (
            <ArticleCard key={article.id} article={article} onClick={onArticleClick} />
          ))}
      </div>

      {/* Terminal footer */}
      <div className="p-3 bg-surface-container-lowest font-mono text-[10px] text-outline/50 border-t border-outline-variant/10 shrink-0">
        &gt; TAIL_LOG -F FEED_INBOUND
      </div>
    </div>
  );
}
