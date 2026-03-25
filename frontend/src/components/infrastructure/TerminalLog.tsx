import { useEffect, useRef } from "react";
import { useLogStream } from "../../hooks/useLogStream";
import { LogLine } from "../shared/log";

function ConnectionDot({ connected }: { connected: boolean }) {
  if (connected) {
    return (
      <span
        className="w-2 h-2 rounded-full bg-tertiary animate-pulse inline-block"
        title="Connected"
      />
    );
  }
  return (
    <span
      className="w-2 h-2 rounded-full bg-outline/40 inline-block"
      title="Disconnected — reconnecting…"
    />
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function TerminalLog() {
  const { logs, connected } = useLogStream(500);

  // scrollEndRef sits at the bottom of the log list.
  const scrollEndRef = useRef<HTMLDivElement>(null);
  // containerRef tracks the scroll container so we can detect whether the
  // user has scrolled up (i.e. is reading older entries).
  const containerRef = useRef<HTMLDivElement>(null);
  // Track whether the user is at the bottom. We only auto-scroll when they
  // are, so scrolling up to read history isn't interrupted by new messages.
  const isAtBottomRef = useRef(true);

  useEffect(() => {
    if (isAtBottomRef.current) {
      scrollEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  function handleScroll() {
    const el = containerRef.current;
    if (!el) return;
    // Consider "at bottom" if within 30px of the end — accounts for
    // sub-pixel rounding and the blinking cursor element.
    isAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 30;
  }

  return (
    <div className="flex-1 bg-surface-container-low border border-outline-variant/15 flex flex-col min-h-0">
      {/* Terminal chrome bar */}
      <div className="bg-surface-container-highest px-4 py-2 flex justify-between items-center shrink-0">
        <span className="font-mono text-[10px] font-bold text-on-surface uppercase tracking-widest">
          TERMINAL_OUTPUT
        </span>
        <div className="flex gap-1.5 items-center">
          <span className="w-2 h-2 bg-error/50 inline-block" />
          <ConnectionDot connected={connected} />
        </div>
      </div>

      {/* Log lines */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="p-4 font-mono text-[10px] overflow-y-auto flex-1 space-y-1"
      >
        {logs.length === 0 ? (
          <p className="text-outline/50">
            {connected ? "Waiting for logs…" : "Connecting…"}
          </p>
        ) : (
          logs.map((entry) => (
            <LogLine
              key={entry.id}
              entry={entry}
              className="flex gap-2 items-baseline leading-relaxed"
            />
          ))
        )}
        {/* Invisible anchor scrolled into view on each new log entry */}
        <div ref={scrollEndRef} />
        <p className="text-primary animate-pulse">_</p>
      </div>
    </div>
  );
}
