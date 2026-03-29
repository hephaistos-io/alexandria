import { useState, useEffect, useRef } from "react";

/**
 * Generic polling hook. Fetches `url` immediately on mount, then again every
 * `intervalMs` milliseconds.
 *
 * `url` can be a string or a function that returns a string. When a function
 * is provided, it's called on every poll tick so the URL can include dynamic
 * values like timestamps (e.g. `() => `/api/foo?since=${new Date().toISOString()}`).
 *
 * On error the previous `data` value is preserved so the UI stays stable.
 * Only `error` updates, giving callers the choice of whether to surface it.
 *
 * The fetch is cancelled on unmount via the `cancelled` flag — this prevents
 * stale setState calls if the component unmounts while a request is in flight.
 */
export function usePolling<T>(
  url: string | (() => string),
  intervalMs: number,
): {
  data: T | null;
  loading: boolean;
  error: string | null;
} {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Store the url in a ref so the interval callback always sees the latest
  // value without needing to restart the interval on every url change.
  const urlRef = useRef(url);
  urlRef.current = url;

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const resolvedUrl = typeof urlRef.current === "function"
          ? urlRef.current()
          : urlRef.current;
        const res = await fetch(resolvedUrl);
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
  }, [intervalMs]);

  return { data, loading, error };
}
