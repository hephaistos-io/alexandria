import type { LogEntry } from "../../../hooks/useLogStream";
import { levelClass, formatTimestamp } from "./logStyles";
import { ServiceBadge } from "./ServiceBadge";

interface LogLineProps {
  entry: LogEntry;
  /** Override classes on the wrapper element. Defaults to the flex layout used
   *  by TerminalPage. Pass a plain string to get a simpler inline layout. */
  className?: string;
}

export function LogLine({
  entry,
  className = "flex gap-3 items-baseline group leading-relaxed",
}: LogLineProps) {
  const time = formatTimestamp(entry.ts);

  return (
    <div className={className}>
      <span className="text-outline/40 select-none shrink-0 text-[10px]">{time}</span>
      <ServiceBadge service={entry.service} />
      {entry.logger && (
        <span className="text-outline/40 shrink-0 text-[10px]">{entry.logger}:</span>
      )}
      <span className={`${levelClass(entry.level)} text-[11px] break-all`}>{entry.message}</span>
    </div>
  );
}
