import { AttributionArticleRow } from "./AttributionArticleRow";
import type { AttributionArticle, EntityRoleType } from "../../types/attribution";

interface AttributionArticleTableProps {
  articles: { articles: AttributionArticle[]; total: number } | null;
  loading: boolean;
  enabledRoleTypes: EntityRoleType[];
  onUpdateRoles: (articleId: number, roles: Record<string, string>) => Promise<boolean>;
}

export function AttributionArticleTable({
  articles,
  loading,
  enabledRoleTypes,
  onUpdateRoles,
}: AttributionArticleTableProps) {
  const hasArticles = articles !== null && articles.articles.length > 0;

  return (
    <section className="bg-surface-container-low relative">
      {/* Corner accent decorations */}
      <div className="absolute -top-[1px] -left-[1px] w-2 h-2 border-t border-l border-primary/40" />
      <div className="absolute -top-[1px] -right-[1px] w-2 h-2 border-t border-r border-primary/40" />
      <div className="absolute -bottom-[1px] -left-[1px] w-2 h-2 border-b border-l border-primary/40" />
      <div className="absolute -bottom-[1px] -right-[1px] w-2 h-2 border-b border-r border-primary/40" />

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-surface-container-lowest border-b border-outline-variant/10">
              <th className="py-4 px-6 font-mono text-[10px] text-outline font-bold uppercase tracking-tighter">
                REF_ID
              </th>
              <th className="py-4 px-6 font-mono text-[10px] text-outline font-bold uppercase tracking-tighter">
                SOURCE_ORIGIN
              </th>
              <th className="py-4 px-6 font-mono text-[10px] text-outline font-bold uppercase tracking-tighter">
                TITLE
              </th>
              <th className="py-4 px-6 font-mono text-[10px] text-outline font-bold uppercase tracking-tighter">
                DATE_INGESTED
              </th>
              <th className="py-4 px-6 font-mono text-[10px] text-outline font-bold uppercase tracking-tighter">
                STATUS
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/5">
            {loading && (
              <tr>
                <td colSpan={5} className="py-12 text-center">
                  <span className="font-mono text-[10px] text-outline uppercase tracking-widest">
                    LOADING...
                  </span>
                </td>
              </tr>
            )}

            {!loading && !hasArticles && (
              <tr>
                <td colSpan={5} className="py-12 text-center">
                  <span className="font-mono text-[10px] text-outline uppercase tracking-widest">
                    NO_ENTRIES_FOUND
                  </span>
                </td>
              </tr>
            )}

            {!loading &&
              hasArticles &&
              articles.articles.map((article) => (
                <AttributionArticleRow
                  key={article.id}
                  article={article}
                  enabledRoleTypes={enabledRoleTypes}
                  onUpdateRoles={onUpdateRoles}
                />
              ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
