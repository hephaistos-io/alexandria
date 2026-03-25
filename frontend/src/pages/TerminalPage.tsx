import { useState, useRef, useEffect, useMemo } from "react";
import { useLogStream } from "../hooks/useLogStream";
import { useInfraStatus } from "../hooks/useInfraStatus";
import { MaterialIcon } from "../components/shared/MaterialIcon";
import { formatTimestamp, LogLine } from "../components/shared/log";

// ── Constants ─────────────────────────────────────────────────────────────────

const INFRA_EXCLUSIONS = new Set([
  "frontend",
  "monitoring-api",
  "postgres",
  "rabbitmq",
  "redis",
  "base",
]);

// ── Utilities ─────────────────────────────────────────────────────────────────

function formatUptimeSeconds(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
}

// ── Main component ─────────────────────────────────────────────────────────────

export function TerminalPage() {
  const { logs, connected } = useLogStream(500);
  const { data: infraData } = useInfraStatus();

  const [activeFilter, setActiveFilter] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [dismissedErrorIds, setDismissedErrorIds] = useState<Set<number>>(new Set());

  const logContainerRef = useRef<HTMLDivElement>(null);
  const scrollEndRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);

  // Auto-scroll only when the user is already at the bottom
  useEffect(() => {
    if (isAtBottomRef.current) {
      scrollEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  function handleScroll() {
    const el = logContainerRef.current;
    if (!el) return;
    isAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 30;
  }

  // Group containers by name, excluding infra services
  const serviceGroups = useMemo(() => {
    if (!infraData) return [];
    const groups = new Map<string, { allRunning: boolean }>();
    for (const c of infraData.containers) {
      if (INFRA_EXCLUSIONS.has(c.name)) continue;
      const existing = groups.get(c.name);
      const isRunning = c.status === "running";
      if (!existing) {
        groups.set(c.name, { allRunning: isRunning });
      } else {
        groups.set(c.name, { allRunning: existing.allRunning && isRunning });
      }
    }
    return Array.from(groups.entries()).map(([name, meta]) => ({ name, ...meta }));
  }, [infraData]);

  // Filter logs by active service and search query
  const filteredLogs = useMemo(() => {
    return logs.filter((entry) => {
      if (activeFilter !== null && entry.service !== activeFilter) return false;
      if (searchQuery.trim() !== "") {
        return entry.message.toLowerCase().includes(searchQuery.toLowerCase());
      }
      return true;
    });
  }, [logs, activeFilter, searchQuery]);

  // Collect errors/warnings for the side panel, excluding dismissed
  const errorPanelEntries = useMemo(() => {
    return logs
      .filter(
        (entry) =>
          (entry.level === "error" || entry.level === "warning") &&
          !dismissedErrorIds.has(entry.id),
      )
      .sort((a, b) => b.ts.localeCompare(a.ts));
  }, [logs, dismissedErrorIds]);

  function dismissError(id: number) {
    setDismissedErrorIds((prev) => new Set(prev).add(id));
  }

  // Footer stats derived from infra containers
  const runningCount = infraData?.containers.filter((c) => c.status === "running").length ?? 0;
  const avgUptimeSeconds = useMemo(() => {
    const running = infraData?.containers.filter((c) => c.status === "running") ?? [];
    if (running.length === 0) return 0;
    return running.reduce((sum, c) => sum + c.uptime_seconds, 0) / running.length;
  }, [infraData]);

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* ── Filter bar ─────────────────────────────────────────────────────── */}
      <div className="h-14 bg-surface-container-low flex items-center px-6 gap-3 border-b border-outline-variant/10 shrink-0 overflow-x-auto">
        <span className="text-[10px] font-mono text-outline uppercase tracking-tighter shrink-0 mr-2">
          Active_Nodes:
        </span>

        <button
          onClick={() => setActiveFilter(null)}
          className={`px-3 py-1 text-[10px] font-mono shrink-0 transition-colors ${
            activeFilter === null
              ? "bg-primary text-on-primary"
              : "bg-surface-container-high text-on-surface border border-outline-variant/30 hover:bg-surface-container-highest"
          }`}
        >
          ALL_TRAFFIC
        </button>

        {serviceGroups.map(({ name, allRunning }) => (
          <button
            key={name}
            onClick={() => setActiveFilter(name === activeFilter ? null : name)}
            className={`px-3 py-1 text-[10px] font-mono flex items-center gap-1.5 shrink-0 transition-colors ${
              activeFilter === name
                ? "bg-primary text-on-primary"
                : "bg-surface-container-high text-on-surface border border-outline-variant/30 hover:bg-surface-container-highest"
            }`}
          >
            <span>{name.toUpperCase()}</span>
            <span className={`text-[8px] ${allRunning ? "text-tertiary" : "text-error"}`}>
              {allRunning ? "UP" : "ERR"}
            </span>
          </button>
        ))}
      </div>

      {/* ── Middle area ─────────────────────────────────────────────────────── */}
      <div className="flex-1 flex overflow-hidden">

        {/* ── Log feed ─────────────────────────────────────────────────────── */}
        <section className="flex-1 bg-surface flex flex-col relative overflow-hidden">
          {/* LIVE_FEED watermark */}
          <div className="absolute top-4 right-8 opacity-[0.07] pointer-events-none select-none z-0">
            <p className="text-[40px] font-headline font-black leading-none tracking-tighter text-on-surface uppercase">
              LIVE_FEED
            </p>
          </div>

          <div
            ref={logContainerRef}
            onScroll={handleScroll}
            className="flex-1 p-6 font-mono text-[11px] overflow-y-auto space-y-1.5 relative z-10"
          >
            {filteredLogs.length === 0 ? (
              <p className="text-outline/50">
                {connected ? "Waiting for logs..." : "Connecting..."}
              </p>
            ) : (
              filteredLogs.map((entry) => <LogLine key={entry.id} entry={entry} />)
            )}
            <div ref={scrollEndRef} />
            <p className="text-primary animate-pulse">_</p>
          </div>
        </section>

        {/* ── Error panel ──────────────────────────────────────────────────── */}
        <aside className="w-80 bg-surface-container-low flex flex-col border-l border-outline-variant/10 shrink-0">
          {/* Panel header */}
          <div className="p-4 bg-surface-container flex items-center justify-between shrink-0">
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 bg-error" />
              <h3 className="font-headline font-bold text-xs uppercase tracking-widest text-on-surface">
                SYSTEM_ERRORS
              </h3>
            </div>
            <span className="text-[10px] font-mono text-error bg-error/10 px-2">
              {errorPanelEntries.length}_ACTIVE
            </span>
          </div>

          {/* Error cards */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {errorPanelEntries.length === 0 && (
              <p className="text-[10px] font-mono text-outline/50 uppercase">No active alerts</p>
            )}

            {errorPanelEntries.map((entry) => {
              const isError = entry.level === "error";
              return (
                <div
                  key={entry.id}
                  className={`p-4 ${isError ? "bg-surface-container-highest border-l-4 border-error" : "bg-surface-container border-l-4 border-primary"}`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <span className={`text-[10px] font-mono font-bold uppercase ${isError ? "text-error" : "text-primary"}`}>
                      {isError ? "CRITICAL" : "WARNING"}
                    </span>
                    <span className="text-[10px] font-mono text-outline opacity-50">
                      {formatTimestamp(entry.ts)}
                    </span>
                  </div>

                  <p className="text-[11px] font-mono text-on-surface mb-1 break-words">
                    {entry.message.length > 60 ? `${entry.message.slice(0, 60)}...` : entry.message}
                  </p>

                  <p className="text-[10px] font-mono text-outline mb-3">
                    Service: {entry.service}
                  </p>

                  <button
                    onClick={() => dismissError(entry.id)}
                    className="w-full py-1 text-[9px] font-mono border border-outline-variant/30 text-on-surface uppercase hover:bg-surface transition-colors"
                  >
                    Acknowledge
                  </button>
                </div>
              );
            })}
          </div>

          {/* Footer stats */}
          <div className="p-4 bg-surface-container-low border-t border-outline-variant/20 shrink-0">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-[9px] font-mono text-outline uppercase mb-1">Avg Uptime</p>
                <p className="text-sm font-mono text-tertiary">
                  {avgUptimeSeconds > 0 ? formatUptimeSeconds(avgUptimeSeconds) : "—"}
                </p>
              </div>
              <div>
                <p className="text-[9px] font-mono text-outline uppercase mb-1">Running</p>
                <p className="text-sm font-mono text-primary">{runningCount}</p>
              </div>
            </div>
          </div>
        </aside>
      </div>

      {/* ── Bottom bar ──────────────────────────────────────────────────────── */}
      <div className="h-12 bg-surface border-t border-outline-variant/30 flex items-center px-6 shrink-0">
        <MaterialIcon name="chevron_right" className="text-primary text-base mr-1" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="FILTER_LOGS..."
          className="bg-transparent border-none outline-none flex-1 font-mono text-sm text-on-surface placeholder-outline/30 focus:ring-0"
        />
        <div className="flex items-center gap-2 text-[10px] font-mono select-none">
          {connected ? (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-tertiary animate-pulse" />
              <span className="text-tertiary">ONLINE</span>
            </>
          ) : (
            <>
              <span className="w-1.5 h-1.5 rounded-full border border-outline/60" />
              <span className="text-outline">OFFLINE</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
