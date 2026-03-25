import { Link } from "react-router";
import type { ArchiveArticle } from "../../types/archive";
import { formatDate } from "../../utils/formatDate";
import { buildRefId } from "../../utils/buildRefId";

interface TagChipProps {
  label: string;
  variant: "automatic" | "manual" | "pending";
}

interface ArchiveCardProps {
  article: ArchiveArticle;
}

function TagChip({ label, variant }: TagChipProps) {
  const classes: Record<TagChipProps["variant"], string> = {
    automatic:
      "bg-primary/10 border border-primary/20 text-primary",
    manual:
      "bg-tertiary/10 border border-tertiary/20 text-tertiary",
    pending:
      "bg-outline-variant/20 border border-outline-variant/30 text-on-surface-variant",
  };

  return (
    <span className={`px-2 py-0.5 font-mono text-[9px] ${classes[variant]}`}>
      [{label.toUpperCase()}]
    </span>
  );
}

export function ArchiveCard({ article }: ArchiveCardProps) {
  const refId = buildRefId(article.id);
  const date = formatDate(article.published_at ?? article.created_at);

  const hasLabels =
    (article.automatic_labels && article.automatic_labels.length > 0) ||
    (article.manual_labels && article.manual_labels.length > 0);

  return (
    <Link
      to={`/archive/${article.id}`}
      className="group bg-surface-container-low flex flex-col transition-all hover:bg-surface-container border-l-2 border-transparent hover:border-primary"
    >
      {/* Card header: REF_ID + date */}
      <div className="bg-surface-container-highest px-4 py-2 flex justify-between items-center border-b border-outline-variant/10">
        <span className="font-mono text-[10px] text-primary font-bold tracking-tighter">
          {refId}
        </span>
        <span className="font-mono text-[9px] text-outline">{date}</span>
      </div>

      {/* Card body: title, summary, tags */}
      <div className="p-5 flex-1 flex flex-col">
        <h3 className="font-headline font-bold text-base text-on-surface group-hover:text-primary transition-colors mb-3 leading-snug">
          {article.title}
        </h3>

        {article.summary ? (
          <p className="text-on-surface-variant text-xs leading-relaxed mb-6 font-body opacity-80 line-clamp-3">
            {article.summary}
          </p>
        ) : (
          <p className="text-on-surface-variant/40 text-xs leading-relaxed mb-6 font-mono italic">
            [NO_SUMMARY_AVAILABLE]
          </p>
        )}

        {/* Tags pushed to the bottom of the card */}
        <div className="mt-auto flex flex-wrap gap-2">
          {hasLabels ? (
            <>
              {article.automatic_labels?.map((label) => (
                <TagChip key={`auto-${label}`} label={label} variant="automatic" />
              ))}
              {article.manual_labels?.map((label) => (
                <TagChip key={`manual-${label}`} label={label} variant="manual" />
              ))}
            </>
          ) : (
            <TagChip label="PENDING" variant="pending" />
          )}
        </div>
      </div>
    </Link>
  );
}
