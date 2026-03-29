import { Link } from "react-router";

export interface ArticleDetailData {
  id: string | number;
  title: string;
  summary: string | null;
  category: string;
  date: string;
  location?: string;
  source: string;
  labels: string[];
  /** When set, renders an "OPEN_ARTICLE" link. Omit to hide it (e.g. for conflicts). */
  linkTo?: string;
}

interface ArticleDetailCardProps {
  article: ArticleDetailData;
  /** Label shown above the card (e.g. "SELECTED_INTERCEPT", "RELATED_ARTICLE"). */
  sectionLabel?: string;
  /** Whether to show the section label header row. Defaults to true. */
  showHeader?: boolean;
  onDismiss?: () => void;
}

/**
 * Expanded article detail card — reusable across map selection, event focus,
 * and anywhere else an article needs a rich preview.
 */
export function ArticleDetailCard({
  article,
  sectionLabel = "SELECTED_INTERCEPT",
  showHeader = true,
  onDismiss,
}: ArticleDetailCardProps) {
  return (
    <div className="shrink-0 border-b border-outline-variant/10 animate-[slideDown_150ms_ease-out]">
      {/* Section label */}
      {showHeader && (
        <div className="px-4 pt-3 pb-1.5 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 bg-primary shadow-[0_0_6px_var(--color-primary)]" />
            <span className="font-mono text-[9px] text-primary uppercase tracking-widest">
              {sectionLabel}
            </span>
          </div>
          {onDismiss && (
            <button
              onClick={onDismiss}
              className="font-mono text-[9px] text-outline/50 hover:text-on-surface border border-outline-variant/30 hover:border-outline-variant/60 px-2 py-0.5 uppercase tracking-wider transition-colors"
            >
              RESET
            </button>
          )}
        </div>
      )}

      {/* Card body with left accent border and glow background */}
      <div className="mx-3 mb-3 p-3 border-l-2 border-primary bg-primary/[0.06] shadow-[inset_0_0_20px_rgba(118,169,250,0.04)]">
        {/* Category + date row */}
        <div className="flex justify-between items-start mb-2">
          <span className="font-mono text-[9px] text-tertiary uppercase tracking-wider">
            {article.category}
          </span>
          <span className="font-mono text-[10px] text-outline">
            {article.date}
          </span>
        </div>

        {/* Location (optional — not all sources have geo data) */}
        {article.location && (
          <div className="font-mono text-[9px] text-primary/60 uppercase tracking-widest mb-1">
            {article.location}
          </div>
        )}

        {/* Article title */}
        <h4 className="font-headline text-sm font-bold text-on-surface mb-2">
          {article.title}
        </h4>

        {/* Summary */}
        {article.summary && (
          <p className="text-xs text-on-surface-variant leading-relaxed mb-3 line-clamp-4">
            {article.summary}
          </p>
        )}

        {/* Topic labels */}
        {article.labels.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-3">
            {article.labels.map((lbl) => (
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
            SRC: {article.source}
          </span>
          {article.linkTo && (
            <Link
              to={article.linkTo}
              className="font-mono text-[9px] text-primary hover:text-tertiary transition-colors uppercase tracking-wider"
            >
              OPEN_ARTICLE →
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
