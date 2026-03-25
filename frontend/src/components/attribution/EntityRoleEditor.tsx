import { useState } from "react";
import type { AttributionArticle, EntityRoleType } from "../../types/attribution";
import { GEO_LABELS, entityKey } from "./attributionHelpers";

interface EntityRoleEditorProps {
  article: AttributionArticle;
  enabledRoleTypes: EntityRoleType[];
  onSave: (articleId: number, roles: Record<string, string>) => Promise<boolean>;
  onClose: () => void;
}

// The expanded row that lets the user assign roles to each geographic entity.
export function EntityRoleEditor({
  article,
  enabledRoleTypes,
  onSave,
  onClose,
}: EntityRoleEditorProps) {
  // Filter to only geographic entities and deduplicate by key.
  // The same entity can appear multiple times at different positions in the text.
  // We keep the first occurrence (which has the earliest char offset).
  const geoEntities = (() => {
    const seen = new Set<string>();
    return (article.entities ?? []).filter((e) => {
      if (!GEO_LABELS.has(e.label)) return false;
      const key = entityKey(e);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  })();

  // Initialize selection state from existing manual roles, falling back
  // to auto_role, then empty string. This mirrors what a user would
  // expect: the pre-existing annotation is shown ready to confirm/edit.
  const initialSelections: Record<string, string> = {};
  for (const entity of geoEntities) {
    const key = entityKey(entity);
    const existingManual = article.manual_entity_roles?.[key];
    initialSelections[key] = existingManual ?? entity.auto_role ?? "";
  }

  const [selections, setSelections] = useState<Record<string, string>>(initialSelections);
  const [saving, setSaving] = useState(false);

  function handleChange(key: string, value: string) {
    setSelections((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSave() {
    // Only send entities that have a role selected — omit blanks.
    const nonEmpty: Record<string, string> = {};
    for (const [key, val] of Object.entries(selections)) {
      if (val !== "") nonEmpty[key] = val;
    }

    setSaving(true);
    const success = await onSave(article.id, nonEmpty);
    setSaving(false);
    if (success) {
      onClose();
    }
  }

  if (geoEntities.length === 0) {
    return (
      <tr className="bg-surface-container-low">
        <td colSpan={5} className="px-6 py-4">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] text-outline uppercase tracking-widest">
              NO_GEO_ENTITIES — no GPE / LOC / FAC entities found in this article
            </span>
            <button
              onClick={onClose}
              className="px-3 py-1 font-mono text-[10px] text-outline border border-outline-variant/30 hover:text-on-surface uppercase tracking-widest"
            >
              CLOSE
            </button>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr className="bg-surface-container-low">
      <td colSpan={5} className="px-6 py-4">
        {/* Title bar */}
        <div className="flex items-center justify-between mb-4">
          <span className="font-mono text-[10px] text-outline uppercase tracking-widest">
            ENTITY_ROLE_ASSIGNMENT // {geoEntities.length} GEO ENTITIES
          </span>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-3 py-1 font-mono text-[10px] text-outline border border-outline-variant/30 hover:text-on-surface uppercase tracking-widest"
            >
              SKIP
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-3 py-1 bg-primary text-on-primary font-headline font-bold text-[10px] uppercase tracking-widest active:scale-95 disabled:opacity-50"
            >
              {saving ? "SAVING..." : "SAVE"}
            </button>
          </div>
        </div>

        {/* Article content for context */}
        <div className="mb-4 bg-surface-container p-4 max-h-48 overflow-y-auto border-l-2 border-primary/30">
          {article.summary && (
            <p className="text-xs text-on-surface/90 mb-2 font-body leading-relaxed">
              {article.summary}
            </p>
          )}
          <p className="text-[11px] text-on-surface/60 font-body leading-relaxed whitespace-pre-line">
            {article.content}
          </p>
        </div>

        {/* Entity rows */}
        <div className="space-y-2">
          {geoEntities.map((entity) => {
            const key = entityKey(entity);
            const displayName = entity.canonical_name ?? entity.text;

            return (
              <div
                key={key}
                className="flex items-center gap-4 py-2 border-b border-outline-variant/10 last:border-0"
              >
                {/* Entity name */}
                <div className="flex-1 min-w-0">
                  <span className="font-mono text-xs text-on-surface truncate block">
                    {displayName}
                  </span>
                  {entity.canonical_name !== null && entity.canonical_name !== entity.text && (
                    <span className="font-mono text-[9px] text-outline truncate block">
                      alias: {entity.text}
                    </span>
                  )}
                </div>

                {/* NER label badge */}
                <span className="font-mono text-[9px] text-outline border border-outline-variant/30 px-2 py-0.5 uppercase shrink-0">
                  {entity.label}
                </span>

                {/* Auto role hint with confidence */}
                {entity.auto_role != null && (
                  <div className="flex items-center gap-1 shrink-0">
                    <span className="font-mono text-[9px] text-primary uppercase">
                      AUTO: {entity.auto_role}
                    </span>
                    {entity.auto_role_confidence !== null && (
                      <span className="font-mono text-[9px] text-outline">
                        ({(entity.auto_role_confidence * 100).toFixed(0)}%)
                      </span>
                    )}
                  </div>
                )}

                {/* Role dropdown */}
                <select
                  value={selections[key] ?? ""}
                  onChange={(e) => handleChange(key, e.target.value)}
                  className="bg-surface-container-high border border-outline-variant/30 text-on-surface font-mono text-[10px] px-2 py-1 uppercase shrink-0"
                >
                  <option value="">— SELECT —</option>
                  {enabledRoleTypes.map((rt) => (
                    <option key={rt.id} value={rt.name}>
                      {rt.name}
                    </option>
                  ))}
                </select>
              </div>
            );
          })}
        </div>
      </td>
    </tr>
  );
}
