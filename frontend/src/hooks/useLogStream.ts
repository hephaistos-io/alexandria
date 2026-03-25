import { useState, useEffect, useRef, useCallback } from "react";

export interface LogEntry {
  id: number;       // Monotonic counter for stable React keys
  ts: string;       // ISO 8601 timestamp
  level: string;    // "info", "warning", "error", "debug"
  service: string;  // "article-fetcher", "article-scraper", etc.
  logger?: string;  // Python logger name (optional)
  message: string;  // The log message
}

const DEFAULT_MAX_LOG_BUFFER = 10;

// Reconnection uses exponential backoff: each failed attempt doubles the
// delay, capped at MAX_RECONNECT_DELAY_MS. A successful connection resets
// the delay back to INITIAL_RECONNECT_DELAY_MS.
const INITIAL_RECONNECT_DELAY_MS = 2500;
const MAX_RECONNECT_DELAY_MS = 30_000;

// Monotonic counter for stable React keys. Lives outside the hook so it
// never resets across re-mounts (e.g. React strict mode double-mount).
let nextEntryId = 0;

export function useLogStream(maxBuffer = DEFAULT_MAX_LOG_BUFFER): { logs: LogEntry[]; connected: boolean } {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);

  // Storing the socket in a ref means we hold a stable reference across
  // re-renders without triggering them ourselves. If we used useState for the
  // socket, setting it would cause an extra render every time we reconnect.
  const socketRef = useRef<WebSocket | null>(null);

  // useRef for the reconnect timer so we can cancel it on unmount without
  // the timer ID becoming a render dependency.
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Current backoff delay. Doubles on each failure, resets on success.
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY_MS);

  // Wrap the connect logic in useCallback so it has a stable identity and
  // can safely be called both on mount and inside the reconnect callback.
  const connect = useCallback(() => {
    // Derive ws:// or wss:// from the page's own protocol so WebSocket
    // connections work correctly under both HTTP and HTTPS.
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.host}/ws/logs`;
    const ws = new WebSocket(url);
    socketRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      // Reset backoff on successful connection.
      reconnectDelayRef.current = INITIAL_RECONNECT_DELAY_MS;
    };

    ws.onmessage = (event: MessageEvent) => {
      let raw: Omit<LogEntry, "id">;
      try {
        raw = JSON.parse(event.data as string);
      } catch {
        // Malformed JSON from the server — skip this message rather than
        // crashing the whole component.
        return;
      }

      const entry: LogEntry = { ...raw, id: nextEntryId++ };

      setLogs((prev) => {
        const next = [...prev, entry];
        // Trim to the rolling buffer limit so memory doesn't grow forever.
        return next.length > maxBuffer
          ? next.slice(next.length - maxBuffer)
          : next;
      });
    };

    ws.onerror = () => {
      // onerror always fires immediately before onclose, so we let onclose
      // handle the reconnect. Setting connected=false here would be redundant.
    };

    ws.onclose = () => {
      setConnected(false);
      // Schedule a reconnect with exponential backoff.
      const delay = reconnectDelayRef.current;
      reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY_MS);

      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null;
        connect();
      }, delay);
    };
  }, [maxBuffer]);

  useEffect(() => {
    connect();

    return () => {
      // Cancel any pending reconnect so we don't open a new socket after
      // the component has unmounted.
      if (reconnectTimerRef.current !== null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }

      // Close the socket without triggering the onclose reconnect path.
      // We null out the handlers first so onclose won't schedule a new timer.
      const ws = socketRef.current;
      if (ws) {
        ws.onopen = null;
        ws.onmessage = null;
        ws.onerror = null;
        ws.onclose = null;
        ws.close();
        socketRef.current = null;
      }
    };
  }, [connect]);

  return { logs, connected };
}
