import type { DashboardArticle } from "../../types/dashboard";
import { formatDate } from "../../utils/formatDate";
import { buildRefId } from "../../utils/buildRefId";

interface ArticleCardProps {
  article: DashboardArticle;
  onClick?: (articleId: number) => void;
}

export function ArticleCard({ article, onClick }: ArticleCardProps) {
  const refId = buildRefId(article.id);

  // Prefer automatic labels (model output), fall back to manual, then "PENDING"
  // if neither has been assigned yet.
  const tag =
    article.automatic_labels?.[0] ?? article.manual_labels?.[0] ?? "PENDING";

  const timestamp = formatDate(article.published_at ?? article.created_at);

  return (
    <div
      className="group p-3 border-l-2 border-transparent hover:border-primary hover:bg-surface-container/50 transition-all cursor-pointer"
      onClick={() => onClick?.(article.id)}
    >
      {/* Row 1: hex ID + timestamp */}
      <div className="flex justify-between items-center mb-1.5">
        <span className="font-mono text-[9px] text-outline/40">{refId}</span>
        <span className="font-mono text-[9px] text-outline/40">{timestamp}</span>
      </div>

      {/* Title */}
      <h3 className="font-headline text-sm font-bold text-on-surface-variant group-hover:text-primary-container leading-snug line-clamp-2">
        {article.title}
      </h3>

      {/* Summary */}
      <p className="font-body text-xs text-on-surface-variant/60 mt-1 line-clamp-2">
        {article.summary}
      </p>

      {/* Row 2: topic tag + origin */}
      <div className="flex justify-between items-center mt-2 pt-2 border-t border-outline-variant/10">
        <span className="font-mono text-[9px] bg-surface-container px-1.5 py-0.5 text-outline">
          #{tag}
        </span>
        <span className="font-mono text-[9px] text-outline/40">
          {article.origin}
        </span>
      </div>
    </div>
  );
}
