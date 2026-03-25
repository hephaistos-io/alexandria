import { useState, useEffect } from "react";

/**
 * Generic polling hook. Fetches `url` immediately on mount, then again every
 * `intervalMs` milliseconds.
 *
 * On error the previous `data` value is preserved so the UI stays stable.
 * Only `error` updates, giving callers the choice of whether to surface it.
 *
 * The fetch is cancelled on unmount via the `cancelled` flag — this prevents
 * stale setState calls if the component unmounts while a request is in flight.
 */
export function usePolling<T>(
  url: string,
  intervalMs: number,
): {
  data: T | null;
  loading: boolean;
  error: string | null;
} {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        const json: T = await res.json();
        if (!cancelled) {
          setData(json);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          // Keep previous data on error so the display stays stable.
          setError(e instanceof Error ? e.message : "Failed to fetch");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    poll();
    const intervalId = setInterval(poll, intervalMs);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [url, intervalMs]);

  return { data, loading, error };
}
