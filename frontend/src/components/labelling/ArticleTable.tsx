import { ArticleRow } from "./ArticleRow";
import type { ArticlePage } from "../../types/labelling";
import type { ClassificationLabel } from "../../types/classification";

interface ArticleTableProps {
  articles: ArticlePage | null;
  loading: boolean;
  availableLabels: ClassificationLabel[];
  onUpdateLabels: (articleId: number, labels: string[]) => Promise<boolean>;
}

export function ArticleTable({ articles, loading, availableLabels, onUpdateLabels }: ArticleTableProps) {
  const hasArticles = articles !== null && articles.articles.length > 0;

  return (
    <section className="bg-surface-container-low relative">
      {/* Corner accent decorations — small L-shaped borders that give
          the table a "tactical overlay" feel, matching the UX mockup. */}
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
                DATE_INGESTED
              </th>
              <th className="py-4 px-6 font-mono text-[10px] text-outline font-bold uppercase tracking-tighter">
                MANUAL_LABELS
              </th>
              <th className="py-4 px-6 font-mono text-[10px] text-outline font-bold uppercase tracking-tighter">
                AUTO_LABELS
              </th>
              <th className="py-4 px-6 font-mono text-[10px] text-outline font-bold uppercase tracking-tighter text-right">
                ACTIONS
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/5">
            {loading && (
              <tr>
                <td colSpan={6} className="py-12 text-center">
                  <span className="font-mono text-[10px] text-outline uppercase tracking-widest">
                    LOADING...
                  </span>
                </td>
              </tr>
            )}

            {!loading && !hasArticles && (
              <tr>
                <td colSpan={6} className="py-12 text-center">
                  <span className="font-mono text-[10px] text-outline uppercase tracking-widest">
                    NO_ENTRIES_FOUND
                  </span>
                </td>
              </tr>
            )}

            {!loading &&
              hasArticles &&
              articles.articles.map((article) => (
                <ArticleRow
                  key={article.id}
                  article={article}
                  availableLabels={availableLabels}
                  onUpdateLabels={onUpdateLabels}
                />
              ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
