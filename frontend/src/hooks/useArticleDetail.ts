import { useState, useEffect } from "react";
import type { ArticleDetail } from "../types/archive";

export function useArticleDetail(articleId: number | null): {
  article: ArticleDetail | null;
  loading: boolean;
  error: string | null;
} {
  const [article, setArticle] = useState<ArticleDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Do nothing when there is no ID to fetch — keeps the hook safe to call
    // even before the ID is parsed from the URL.
    if (articleId === null) return;

    let cancelled = false;

    async function fetchArticle() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`/api/archive/articles/${articleId}`);
        if (!response.ok) {
          throw new Error(`Server returned ${response.status}`);
        }
        const json: ArticleDetail = await response.json();
        if (!cancelled) {
          setArticle(json);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to fetch article");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchArticle();

    return () => {
      cancelled = true;
    };
  }, [articleId]);

  return { article, loading, error };
}
