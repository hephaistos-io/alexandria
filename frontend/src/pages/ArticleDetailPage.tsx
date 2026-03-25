import { useState } from "react";
import { useParams, Link, useNavigate } from "react-router";
import { useArticleDetail } from "../hooks/useArticleDetail";
import { MaterialIcon } from "../components/shared/MaterialIcon";
import type { DashboardEntity } from "../types/dashboard";
import { formatDate } from "../utils/formatDate";
import { buildRefId } from "../utils/buildRefId";

// ── Label chip ──────────────────────────────────────────────────────────────
interface LabelChipProps {
  label: string;
  variant: "automatic" | "manual";
}

function LabelChip({ label, variant }: LabelChipProps) {
  const classes =
    variant === "automatic"
      ? "bg-primary/10 border border-primary/20 text-primary"
      : "bg-tertiary/10 border border-tertiary/20 text-tertiary";

  return (
    <span className={`px-2 py-0.5 font-mono text-[9px] ${classes}`}>
      [{label.toUpperCase()}]
    </span>
  );
}

// ── Entity table row ────────────────────────────────────────────────────────
function EntityRow({ entity, index }: { entity: DashboardEntity; index: number }) {
  return (
    <tr
      className={`border-b border-outline-variant/10 hover:bg-surface-container-low transition-colors ${
        index % 2 === 0 ? "" : "bg-surface-container-lowest/30"
      }`}
    >
      <td className="py-2 px-4 text-sm text-on-surface">{entity.text}</td>
      <td className="py-2 px-4">
        <span className="font-mono text-[9px] px-2 py-0.5 bg-primary/10 border border-primary/20 text-primary">
          {entity.label}
        </span>
      </td>
      <td className="py-2 px-4 text-sm text-on-surface-variant">
        {entity.canonical_name ?? "—"}
      </td>
      <td className="py-2 px-4">
        {entity.wikidata_id ? (
          <a
            href={`https://www.wikidata.org/wiki/${entity.wikidata_id}`}
            target="_blank"
            rel="noreferrer"
            className="font-mono text-[10px] text-tertiary hover:underline"
          >
            {entity.wikidata_id}
          </a>
        ) : (
          <span className="text-outline/40">—</span>
        )}
      </td>
      <td className="py-2 px-4 font-mono text-[10px] text-outline">
        {entity.latitude != null && entity.longitude != null
          ? `${entity.latitude.toFixed(4)}, ${entity.longitude.toFixed(4)}`
          : "—"}
      </td>
    </tr>
  );
}

// ── Loading spinner ─────────────────────────────────────────────────────────
function LoadingState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4">
      <MaterialIcon name="hourglass_top" className="text-4xl text-outline/40 animate-spin" />
      <p className="font-mono text-[10px] text-outline uppercase tracking-widest">
        FETCHING_SIGNAL_DATA...
      </p>
    </div>
  );
}

// ── Error state ─────────────────────────────────────────────────────────────
function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4">
      <MaterialIcon name="error_outline" className="text-4xl text-error/60" />
      <p className="font-mono text-[10px] text-error uppercase tracking-widest">
        SIGNAL_FETCH_ERROR
      </p>
      <p className="font-mono text-[9px] text-outline/50">{message}</p>
      <Link
        to="/archive"
        className="mt-4 px-4 py-2 bg-surface-container-high font-mono text-[10px] text-outline uppercase tracking-widest hover:text-on-surface transition-colors"
      >
        RETURN_TO_ARCHIVE
      </Link>
    </div>
  );
}

// ── Main page ───────────────────────────────────────────────────────────────
export function ArticleDetailPage() {
  // useParams returns string values. We parse to int and guard against NaN.
  const { id } = useParams<{ id: string }>();
  const articleId = id !== undefined && !isNaN(parseInt(id, 10)) ? parseInt(id, 10) : null;

  const { article, loading, error } = useArticleDetail(articleId);
  const navigate = useNavigate();
  const [reparsing, setReparsing] = useState(false);

  async function handleReparse() {
    if (!articleId) return;
    const confirmed = window.confirm("Delete this article and re-queue for reprocessing?");
    if (!confirmed) return;

    setReparsing(true);
    try {
      const response = await fetch(`/api/archive/articles/${articleId}/reparse`, {
        method: "POST",
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `HTTP ${response.status}`);
      }
      navigate("/archive");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      alert("Reparse failed: " + message);
    } finally {
      setReparsing(false);
    }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Back navigation */}
      <div className="px-6 pt-4 pb-4 border-b border-outline-variant/10 flex items-center gap-4">
        <Link
          to="/archive"
          className="flex items-center gap-2 font-mono text-[10px] text-outline uppercase tracking-widest hover:text-primary transition-colors"
        >
          <MaterialIcon name="chevron_left" className="text-sm" />
          BACK_TO_ARCHIVE
        </Link>
        {article && (
          <>
            <span className="text-outline/20">|</span>
            <span className="font-mono text-[10px] text-outline/50 uppercase">
              {buildRefId(article.id)}
            </span>
          </>
        )}
      </div>

      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} />
      ) : article ? (
        <div className="flex-1 p-6 md:p-8 overflow-y-auto">
          <div className="max-w-4xl mx-auto space-y-8">
            {/* Article header ─────────────────────────────────────── */}
            <div>
              {/* Meta row */}
              <div className="flex items-center gap-4 mb-4 flex-wrap">
                <span className="font-mono text-[10px] text-primary font-bold">
                  {buildRefId(article.id)}
                </span>
                <span className="font-mono text-[9px] text-outline uppercase">
                  {article.origin}
                </span>
                <span className="font-mono text-[9px] text-outline">
                  {formatDate(article.published_at)}
                </span>
              </div>

              <h1 className="font-headline text-3xl font-black text-on-surface mb-4 leading-tight">
                {article.title}
              </h1>

              {/* Label chips */}
              {((article.automatic_labels && article.automatic_labels.length > 0) ||
                (article.manual_labels && article.manual_labels.length > 0)) && (
                <div className="flex flex-wrap gap-2 mb-4">
                  {article.automatic_labels?.map((label) => (
                    <LabelChip key={`auto-${label}`} label={label} variant="automatic" />
                  ))}
                  {article.manual_labels?.map((label) => (
                    <LabelChip key={`manual-${label}`} label={label} variant="manual" />
                  ))}
                </div>
              )}

              {/* Action buttons */}
              <div className="flex items-center gap-3 flex-wrap">
                <a
                  href={article.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-on-primary font-mono text-[10px] tracking-widest uppercase hover:shadow-[0_0_15px_rgba(169,199,255,0.4)] transition-all active:scale-95"
                >
                  <MaterialIcon name="open_in_new" className="text-sm" />
                  VIEW_SOURCE
                </a>
                <button
                  onClick={handleReparse}
                  disabled={reparsing}
                  className="font-mono text-[10px] px-4 py-2 border border-error/50 text-error hover:bg-error/10 transition-colors uppercase tracking-wider disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {reparsing ? "REPARSING..." : "REPARSE_ARTICLE"}
                </button>
              </div>
            </div>

            {/* Summary block ──────────────────────────────────────── */}
            {article.summary && (
              <div className="p-4 bg-surface-container-low border-l-2 border-primary">
                <p className="font-mono text-[10px] text-outline uppercase mb-2">
                  SUMMARY
                </p>
                <p className="text-on-surface-variant text-sm leading-relaxed">
                  {article.summary}
                </p>
              </div>
            )}

            {/* Article content ────────────────────────────────────── */}
            <div>
              {article.content
                .split(/\n\n+/)
                .filter((p) => p.trim().length > 0)
                .map((paragraph, i) => (
                  <p
                    key={i}
                    className="text-on-surface-variant text-sm leading-relaxed mb-4 font-body"
                  >
                    {paragraph.trim()}
                  </p>
                ))}
            </div>

            {/* Entities table ─────────────────────────────────────── */}
            {article.entities && article.entities.length > 0 && (
              <div>
                <h2 className="font-headline text-lg font-bold text-on-surface mb-4 uppercase tracking-wider">
                  Extracted Entities
                </h2>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-outline-variant/20">
                        <th className="text-left font-mono text-[10px] text-outline uppercase py-3 px-4">
                          Entity
                        </th>
                        <th className="text-left font-mono text-[10px] text-outline uppercase py-3 px-4">
                          Type
                        </th>
                        <th className="text-left font-mono text-[10px] text-outline uppercase py-3 px-4">
                          Canonical
                        </th>
                        <th className="text-left font-mono text-[10px] text-outline uppercase py-3 px-4">
                          Wikidata
                        </th>
                        <th className="text-left font-mono text-[10px] text-outline uppercase py-3 px-4">
                          Coordinates
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {article.entities.map((entity, i) => (
                        <EntityRow key={i} entity={entity} index={i} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Metadata footer ────────────────────────────────────── */}
            <div className="border-t border-outline-variant/10 pt-6 flex flex-wrap gap-6">
              <div>
                <span className="font-mono text-[9px] text-outline uppercase block mb-1">
                  SOURCE
                </span>
                <span className="font-mono text-xs text-on-surface-variant">
                  {article.source}
                </span>
              </div>
              <div>
                <span className="font-mono text-[9px] text-outline uppercase block mb-1">
                  PUBLISHED
                </span>
                <span className="font-mono text-xs text-on-surface-variant">
                  {formatDate(article.published_at)}
                </span>
              </div>
              <div>
                <span className="font-mono text-[9px] text-outline uppercase block mb-1">
                  FETCHED
                </span>
                <span className="font-mono text-xs text-on-surface-variant">
                  {formatDate(article.fetched_at)}
                </span>
              </div>
              <div>
                <span className="font-mono text-[9px] text-outline uppercase block mb-1">
                  SCRAPED
                </span>
                <span className="font-mono text-xs text-on-surface-variant">
                  {formatDate(article.scraped_at)}
                </span>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
