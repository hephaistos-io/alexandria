import { useState } from "react";
import { MaterialIcon } from "../shared/MaterialIcon";
import { LabelChipPicker } from "./LabelChipPicker";
import type { ArticleSummary } from "../../types/labelling";
import type { ClassificationLabel } from "../../types/classification";
import { formatDate } from "../../utils/formatDate";
import { buildRefId } from "../../utils/buildRefId";

interface ArticleRowProps {
  article: ArticleSummary;
  availableLabels: ClassificationLabel[];
  onUpdateLabels: (articleId: number, labels: string[]) => Promise<boolean>;
}

function getLabelColor(name: string, available: ClassificationLabel[]): string | null {
  const match = available.find((l) => l.name === name);
  return match ? `#${match.color.replace(/^#/, "")}` : null;
}

export function ArticleRow({ article, availableLabels, onUpdateLabels }: ArticleRowProps) {
  const [isPickerOpen, setIsPickerOpen] = useState(false);

  const hasManualLabels =
    article.manual_labels !== null && article.manual_labels.length > 0;
  const hasAutoLabels =
    article.automatic_labels !== null && article.automatic_labels.length > 0;
  const isLabelled = hasManualLabels || hasAutoLabels;

  async function handleSave(labels: string[]) {
    const success = await onUpdateLabels(article.id, labels);
    if (success) {
      setIsPickerOpen(false);
    }
  }

  return (
    <>
      <tr className="hover:bg-surface-container/50 transition-colors group">
        {/* REF_ID */}
        <td className="py-4 px-6 font-mono text-xs text-primary font-medium tracking-tight">
          {buildRefId(article.id)}
        </td>

        {/* SOURCE_ORIGIN */}
        <td className="py-4 px-6 font-body text-xs text-on-surface-variant">
          {article.origin}
        </td>

        {/* DATE_INGESTED */}
        <td className="py-4 px-6 font-mono text-[10px] text-outline">
          {formatDate(article.created_at)}
        </td>

        {/* MANUAL_LABELS */}
        <td className="py-4 px-6">
          <div className="flex flex-wrap gap-1.5">
            {hasManualLabels &&
              article.manual_labels!.map((name) => {
                const color = getLabelColor(name, availableLabels);
                const chipStyle = color
                  ? {
                      backgroundColor: `${color}1a`,
                      color,
                      borderColor: `${color}33`,
                    }
                  : undefined;
                return (
                  <span
                    key={`manual-${name}`}
                    style={chipStyle}
                    className={`px-2 py-0.5 text-[9px] font-mono border uppercase ${
                      color ? "" : "bg-outline-variant/10 text-outline border-outline-variant/20"
                    }`}
                  >
                    {name}
                  </span>
                );
              })}
            {!hasManualLabels && (
              <span className="text-[9px] font-mono text-outline/40 italic uppercase">
                —
              </span>
            )}
          </div>
        </td>

        {/* AUTO_LABELS */}
        <td className="py-4 px-6">
          <div className="flex flex-wrap gap-1.5">
            {hasAutoLabels &&
              article.automatic_labels!.map((name) => {
                const color = getLabelColor(name, availableLabels);
                const chipStyle = color
                  ? {
                      color,
                      borderColor: `${color}33`,
                    }
                  : undefined;
                return (
                  <span
                    key={`auto-${name}`}
                    style={chipStyle}
                    className={`px-2 py-0.5 text-[9px] font-mono border border-dashed uppercase ${
                      color ? "" : "text-outline border-outline-variant/20"
                    }`}
                  >
                    {name}
                  </span>
                );
              })}
            {!hasAutoLabels && (
              <span className="text-[9px] font-mono text-outline/40 italic uppercase">
                —
              </span>
            )}
          </div>
        </td>

        {/* ACTIONS */}
        <td className="py-4 px-6 text-right">
          {isLabelled ? (
            <div className="flex justify-end gap-2 opacity-40 group-hover:opacity-100 transition-opacity">
              <button
                onClick={() => setIsPickerOpen(!isPickerOpen)}
                className="p-2 hover:bg-surface-container-highest text-outline hover:text-primary"
              >
                <MaterialIcon name="edit_note" className="text-sm" />
              </button>
            </div>
          ) : (
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setIsPickerOpen(!isPickerOpen)}
                className="px-3 py-1 bg-primary text-on-primary font-headline font-bold text-[10px] uppercase tracking-widest active:scale-95"
              >
                LABEL ENTRY
              </button>
            </div>
          )}
        </td>
      </tr>

      {/* Inline label picker */}
      {isPickerOpen && (
        <tr className="bg-surface-container-low">
          <td colSpan={6} className="px-6 py-2">
            <LabelChipPicker
              availableLabels={availableLabels}
              currentLabels={article.manual_labels ?? []}
              onSave={handleSave}
              onCancel={() => setIsPickerOpen(false)}
            />
          </td>
        </tr>
      )}
    </>
  );
}
