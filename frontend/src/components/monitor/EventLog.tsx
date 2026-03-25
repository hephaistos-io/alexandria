import { MOCK_EVENTS } from "../../data/mock-events";
import type { EventLogEntry } from "../../types/pipeline";

const LEVEL_TIMESTAMP_CLASS: Record<EventLogEntry["level"], string> = {
  system: "text-tertiary/70",
  info: "text-primary/70",
  success: "text-primary/70",
  warning: "text-outline/50",
  error: "text-error/70",
};

function renderMessage(entry: EventLogEntry) {
  if (!entry.highlight) {
    return <span className="text-on-surface">{entry.message}</span>;
  }

  const parts = entry.message.split(entry.highlight);

  return (
    <span className="text-on-surface">
      {parts.map((part, i) => (
        <span key={i}>
          {part}
          {i < parts.length - 1 && (
            <span className="text-tertiary">{entry.highlight}</span>
          )}
        </span>
      ))}
    </span>
  );
}

export function EventLog() {
  return (
    <div className="bg-surface-container-low p-6 col-span-12 lg:col-span-9 flex flex-col">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h3 className="font-headline text-sm font-bold text-on-surface uppercase tracking-widest">
          System Event Log
        </h3>
        <div className="flex gap-2">
          <span className="px-2 py-1 bg-surface-container-highest font-mono text-[9px] text-outline">
            LVL: [ALL]
          </span>
          <span className="px-2 py-1 bg-surface-container-highest font-mono text-[9px] text-outline">
            FILTER: [ACTIVE]
          </span>
        </div>
      </div>

      {/* Log area */}
      <div className="bg-surface-container-lowest font-mono text-xs p-4 overflow-y-auto h-80 mt-4 border border-outline-variant/5 space-y-2">
        {MOCK_EVENTS.map((entry, index) => {
          const timestampClass = LEVEL_TIMESTAMP_CLASS[entry.level];

          return (
            <p key={index} className={timestampClass}>
              [{entry.timestamp}]{" "}
              {entry.level === "warning" || entry.level === "error" ? (
                entry.message
              ) : (
                renderMessage(entry)
              )}
            </p>
          );
        })}
      </div>
    </div>
  );
}
