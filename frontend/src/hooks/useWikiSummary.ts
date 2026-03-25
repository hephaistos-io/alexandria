import { useState, useEffect, useRef } from "react";

interface WikiSummaryResult {
  summary: string | null;
  thumbnailUrl: string | null;
  source: "wikipedia" | "wikidata" | null;
  loading: boolean;
}

interface CacheEntry {
  summary: string | null;
  thumbnailUrl: string | null;
  source: "wikipedia" | "wikidata" | null;
}

// Fetches a Wikipedia summary and thumbnail for a given Wikidata QID.
//
// Two-step process:
//   1. Wikibase REST API: resolve QID → English Wikipedia article title
//   2. Wikipedia REST API: fetch summary/thumbnail for that title
//
// Results are cached in a ref-backed Map so repeated renders for the same
// QID don't fire duplicate network requests. The cache is per-component-
// instance (not global), which is fine for this use case.
export function useWikiSummary(qid: string | null): WikiSummaryResult {
  const [result, setResult] = useState<CacheEntry>({ summary: null, thumbnailUrl: null, source: null });
  const [loading, setLoading] = useState(false);

  // useRef gives us a stable Map that survives re-renders without triggering them.
  const cache = useRef(new Map<string, CacheEntry>());

  useEffect(() => {
    if (qid === null || qid.trim() === "") {
      setResult({ summary: null, thumbnailUrl: null, source: null });
      setLoading(false);
      return;
    }

    // Return cached result immediately — no network call needed.
    const cached = cache.current.get(qid);
    if (cached !== undefined) {
      setResult(cached);
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function fetchSummary() {
      setLoading(true);
      setResult({ summary: null, thumbnailUrl: null, source: null });

      try {
        // Step 1: Get the sitelinks for this entity from Wikibase.
        // The enwiki sitelink gives us the Wikipedia article title.
        const sitelinksRes = await fetch(
          `https://www.wikidata.org/w/rest.php/wikibase/v1/entities/items/${qid}/sitelinks`,
        );

        if (!sitelinksRes.ok) throw new Error("Sitelinks fetch failed");

        // The response is a flat object keyed by site ID, e.g. { enwiki: { title: "..." } }
        const sitelinks = await sitelinksRes.json();
        const enwikiTitle: string | undefined = sitelinks?.enwiki?.title;

        if (!enwikiTitle) {
          // No English Wikipedia article — fall back to the Wikidata description.
          // Most entities have at least a short description (e.g. "Ming dynasty person").
          const itemRes = await fetch(
            `https://www.wikidata.org/w/rest.php/wikibase/v1/entities/items/${qid}`,
          );
          let fallbackSummary: string | null = null;
          if (itemRes.ok) {
            const itemData = await itemRes.json();
            fallbackSummary = itemData?.descriptions?.en ?? null;
          }
          const entry: CacheEntry = { summary: fallbackSummary, thumbnailUrl: null, source: fallbackSummary ? "wikidata" : null };
          cache.current.set(qid, entry);
          if (!cancelled) {
            setResult(entry);
            setLoading(false);
          }
          return;
        }

        // Step 2: Fetch the Wikipedia summary for that article title.
        // The REST summary endpoint returns a clean extract + optional thumbnail.
        const summaryRes = await fetch(
          `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(enwikiTitle)}`,
        );

        if (!summaryRes.ok) throw new Error("Wikipedia summary fetch failed");

        const data = await summaryRes.json();
        const entry: CacheEntry = {
          summary: data.extract ?? null,
          thumbnailUrl: data.thumbnail?.source ?? null,
          source: "wikipedia",
        };

        cache.current.set(qid, entry);
        if (!cancelled) {
          setResult(entry);
        }
      } catch {
        // Treat all errors as graceful empty states — the popup just won't
        // show a summary/image rather than surfacing an error to the user.
        const entry: CacheEntry = { summary: null, thumbnailUrl: null, source: null };
        cache.current.set(qid, entry);
        if (!cancelled) {
          setResult(entry);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchSummary();

    // Cleanup: if the QID changes before the fetch completes, ignore stale results.
    return () => {
      cancelled = true;
    };
  }, [qid]);

  return { summary: result.summary, thumbnailUrl: result.thumbnailUrl, source: result.source, loading };
}
