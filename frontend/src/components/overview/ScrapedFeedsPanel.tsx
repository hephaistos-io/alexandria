import { ArticleCard } from "./ArticleCard";
import { ArticleDetailCard } from "./ArticleDetailCard";
import type { ArticleDetailData } from "./ArticleDetailCard";
import type { DashboardArticle } from "../../types/dashboard";
import type { DetectedEventDetail, EventArticle } from "../../types/event";
import type { GeoAnchor } from "../../types/pipeline";
import { formatDate } from "../../utils/formatDate";

/** Map a GeoAnchor (map marker selection) to the generic detail card shape. */
function anchorToDetail(a: GeoAnchor): ArticleDetailData {
  return {
    id: a.id,
    title: a.label,
    summary: a.summary,
    category: a.category,
    date: a.date,
    location: a.city,
    source: a.source,
    labels: a.labels,
    linkTo: `/archive/${a.id}`,
  };
}

/** Map an EventArticle (event focus view) to the generic detail card shape. */
function eventArticleToDetail(a: EventArticle): ArticleDetailData {
  return {
    id: a.id,
    title: a.title,
    summary: a.summary,
    category: a.automatic_labels?.[0] ?? "PENDING",
    date: formatDate(a.published_at),
    source: a.source,
    labels: a.automatic_labels ?? [],
    linkTo: `/archive/${a.id}`,
  };
}

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
  const isEventFocused = focusedEventId !== null && focusedEventId !== undefined;

  return (
    <div className="w-96 shrink-0 bg-surface-container-low flex flex-col border-l border-outline-variant/10">
      {/* Panel header — always visible */}
      <div className="p-4 border-b border-outline-variant/10 bg-surface-container shrink-0">
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-headline text-lg font-bold text-on-surface">
            SCRAPED_FEEDS
          </h2>
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

      {/* ── Event focus body ──────────────────────────────────────────────── */}
      {isEventFocused && (
        <>
          {/* Event focus sub-header */}
          <div className="px-4 py-2 border-b border-outline-variant/10 bg-surface-container-low shrink-0 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="inline-block w-1 h-1 bg-purple-400 shadow-[0_0_6px_#c084fc]" />
              <span className="font-mono text-[9px] text-purple-400/70 uppercase tracking-widest">
                EVT_{focusedEventId.toString(16).toUpperCase().padStart(5, "0")}
              </span>
            </div>
            <button
              onClick={onClearFocus}
              className="font-mono text-[9px] text-outline/50 hover:text-on-surface border border-outline-variant/30 hover:border-outline-variant/60 px-2 py-0.5 uppercase tracking-wider transition-colors"
            >
              RESET
            </button>
          </div>

          {/* Loading state */}
          {eventDetailLoading && (
            <div className="flex items-center justify-center py-12">
              <span className="font-mono text-[10px] text-outline uppercase tracking-widest">
                LOADING_EVENT...
              </span>
            </div>
          )}

          {/* Fetch failed or still null */}
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

              {/* Conflict count summary */}
              {eventDetail.conflicts.length > 0 && (
                <div className="px-3 py-2 border-b border-outline-variant/10 flex items-center gap-2">
                  <span className="font-mono text-[9px] text-outline/50 uppercase tracking-widest">
                    CONFLICT_EVENTS
                  </span>
                  <span className="font-mono text-[9px] text-purple-400">
                    [{eventDetail.conflicts.length}]
                  </span>
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

              {/* Related articles */}
              <div className="px-1 py-1 space-y-0">
                {eventDetail.articles.length === 0 && (
                  <span className="font-mono text-[9px] text-outline/50 px-3">
                    NO_ARTICLES
                  </span>
                )}
                {eventDetail.articles.map((a) => (
                  <ArticleDetailCard
                    key={a.id}
                    article={eventArticleToDetail(a)}
                    showHeader={false}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Normal feed body ─────────────────────────────────────────────── */}
      {!isEventFocused && (
        <>
          {/* Selected anchor detail card — shown when a map marker is clicked */}
          {selectedAnchor && (
            <ArticleDetailCard article={anchorToDetail(selectedAnchor)} onDismiss={onDismissSelection} />
          )}

          {/* Scrollable article list */}
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
        </>
      )}

      {/* Terminal footer — always visible */}
      <div className="p-3 bg-surface-container-lowest font-mono text-[10px] text-outline/50 border-t border-outline-variant/10 shrink-0">
        &gt; TAIL_LOG -F FEED_INBOUND
      </div>
    </div>
  );
}
