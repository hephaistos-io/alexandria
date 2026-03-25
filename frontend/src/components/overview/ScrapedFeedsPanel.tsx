import { Link } from "react-router";
import { ArticleCard } from "./ArticleCard";
import type { DashboardArticle } from "../../types/dashboard";
import type { GeoAnchor } from "../../types/pipeline";

interface ScrapedFeedsPanelProps {
  articles: DashboardArticle[];
  loading: boolean;
  selectedAnchor?: GeoAnchor | null;
  onArticleClick?: (articleId: number) => void;
  onDismissSelection?: () => void;
}

export function ScrapedFeedsPanel({ articles, loading, selectedAnchor, onArticleClick, onDismissSelection }: ScrapedFeedsPanelProps) {
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

        {/* Filter tag pills */}
        <div className="flex gap-2">
          <span className="bg-surface-container-high px-2 py-1 font-mono text-[9px] text-outline">
            GLOBAL_NET
          </span>
          <span className="bg-surface-container-high px-2 py-1 font-mono text-[9px] text-outline">
            ENCRYPTED
          </span>
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
