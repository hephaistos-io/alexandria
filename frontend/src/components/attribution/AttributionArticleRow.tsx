import { useState } from "react";
import { MaterialIcon } from "../shared/MaterialIcon";
import { EntityRoleEditor } from "./EntityRoleEditor";
import { formatDate } from "../../utils/formatDate";
import { buildRefId } from "../../utils/buildRefId";
import { GEO_LABELS } from "./attributionHelpers";
import type { AttributionArticle, EntityRoleType } from "../../types/attribution";

interface AttributionArticleRowProps {
  article: AttributionArticle;
  enabledRoleTypes: EntityRoleType[];
  onUpdateRoles: (articleId: number, roles: Record<string, string>) => Promise<boolean>;
}

export function AttributionArticleRow({
  article,
  enabledRoleTypes,
  onUpdateRoles,
}: AttributionArticleRowProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const hasManualRoles = article.manual_entity_roles !== null;
  const hasAutoRoles =
    !hasManualRoles &&
    (article.entities ?? []).some((e) => e.auto_role != null && GEO_LABELS.has(e.label));

  // Determine status indicator.
  // Priority: manual annotation > auto roles available > pending.
  const statusIndicator = hasManualRoles ? (
    <div className="flex items-center gap-1.5">
      <span className="w-1.5 h-1.5 bg-tertiary shrink-0" />
      <span className="font-mono text-[9px] text-tertiary uppercase">DONE</span>
    </div>
  ) : hasAutoRoles ? (
    <div className="flex items-center gap-1.5">
      <span className="w-1.5 h-1.5 bg-primary shrink-0" />
      <span className="font-mono text-[9px] text-primary uppercase">AUTO</span>
    </div>
  ) : (
    <div className="flex items-center gap-1.5">
      <span className="w-1.5 h-1.5 bg-outline shrink-0" />
      <span className="font-mono text-[9px] text-outline uppercase">PENDING</span>
    </div>
  );

  return (
    <>
      <tr
        className="hover:bg-surface-container/50 transition-colors group cursor-pointer"
        onClick={() => setIsExpanded((prev) => !prev)}
      >
        {/* REF_ID */}
        <td className="py-4 px-6 font-mono text-xs text-primary font-medium tracking-tight">
          {buildRefId(article.id)}
        </td>

        {/* SOURCE_ORIGIN */}
        <td className="py-4 px-6 font-body text-xs text-on-surface-variant">{article.origin}</td>

        {/* TITLE */}
        <td className="py-4 px-6 font-body text-xs text-on-surface max-w-xs">
          <span className="line-clamp-2">{article.title}</span>
        </td>

        {/* DATE_INGESTED */}
        <td className="py-4 px-6 font-mono text-[10px] text-outline whitespace-nowrap">
          {formatDate(article.created_at)}
        </td>

        {/* STATUS */}
        <td className="py-4 px-6">
          <div className="flex items-center justify-between">
            {statusIndicator}
            <MaterialIcon
              name={isExpanded ? "keyboard_arrow_up" : "keyboard_arrow_down"}
              className="text-sm text-outline opacity-40 group-hover:opacity-100 transition-opacity ml-4"
            />
          </div>
        </td>
      </tr>

      {isExpanded && (
        <EntityRoleEditor
          article={article}
          enabledRoleTypes={enabledRoleTypes}
          onSave={onUpdateRoles}
          onClose={() => setIsExpanded(false)}
        />
      )}
    </>
  );
}
