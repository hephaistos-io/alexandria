/**
 * Generic schema health panel.
 *
 * Renders a two-stat card + enabled-ratio progress bar widget that is reused
 * across Classification, Attribution, and Affiliation schema management tabs.
 *
 * The two stat cards are configurable via `primaryStat` and `secondaryStat` so
 * each domain can show the number that is most meaningful to it:
 *   - Classification / Attribution: total count + enabled %
 *   - Affiliation: total count + directed count
 *
 * All three share the same ENABLED_RATIO progress bar at the bottom.
 */

interface StatCardProps {
  label: string;
  value: string | number;
  valueColor: "primary" | "tertiary";
}

function StatCard({ label, value, valueColor }: StatCardProps) {
  const colorClass = valueColor === "primary" ? "text-primary" : "text-tertiary";
  return (
    <div className="bg-surface-container p-4">
      <p className="font-mono text-[10px] text-outline uppercase mb-1">{label}</p>
      <p className={`font-headline text-3xl font-bold ${colorClass}`}>{value}</p>
    </div>
  );
}

export interface SchemaHealthPanelProps<T> {
  items: T[];
  /** e.g. "LABEL_SCHEMA", "ROLE_SCHEMA", "RELATION_SCHEMA" — shown in the corner badge */
  panelId: string;
  /** Label for the primary stat card — e.g. "Total Labels", "Total Role Types" */
  primaryStatLabel: string;
  /**
   * Optional override for the secondary stat card value.
   * When omitted the panel shows enabled-% as the secondary stat (the default
   * for Classification and Attribution).
   * Pass a custom value + label when you need something else, e.g. directed count
   * for the Affiliation schema.
   */
  secondaryStat?: {
    label: string;
    value: (items: T[]) => string | number;
  };
  /** How to determine whether a given item counts as "enabled" for the ratio bar. */
  getEnabled: (item: T) => boolean;
}

export function SchemaHealthPanel<T>({
  items,
  panelId,
  primaryStatLabel,
  secondaryStat,
  getEnabled,
}: SchemaHealthPanelProps<T>) {
  const total = items.length;
  const enabled = items.filter(getEnabled).length;
  const coveragePct = total > 0 ? Math.round((enabled / total) * 100) : 0;

  // Default secondary stat: enabled-percentage display, matching Classification + Attribution.
  const secondaryLabel = secondaryStat?.label ?? "Enabled";
  const secondaryValue =
    secondaryStat != null
      ? secondaryStat.value(items)
      : total > 0
        ? `${coveragePct}%`
        : "--";

  return (
    <section className="bg-surface-container-low p-6 relative">
      <div className="absolute top-0 right-0 p-2 text-[10px] font-mono text-outline-variant/40 select-none">
        [{panelId}]
      </div>

      <div className="flex items-center gap-2 mb-6">
        <div className="w-1 h-4 bg-tertiary" />
        <h2 className="font-headline text-lg tracking-tight uppercase">Schema Health</h2>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-6">
        <StatCard
          label={primaryStatLabel}
          value={total > 0 ? total : "--"}
          valueColor="primary"
        />
        <StatCard label={secondaryLabel} value={secondaryValue} valueColor="tertiary" />
      </div>

      <div className="space-y-4">
        {/* ENABLED_RATIO progress bar */}
        <div>
          <div className="flex justify-between font-mono text-[10px] mb-2">
            <span>ENABLED_RATIO</span>
            <span className={coveragePct === 100 ? "text-tertiary" : "text-outline"}>
              {total > 0 ? (coveragePct === 100 ? "OPTIMAL" : `${enabled}/${total}`) : "--"}
            </span>
          </div>
          <div className="h-1.5 w-full bg-surface-container flex">
            {total > 0 && (
              <>
                <div
                  className="h-full bg-primary transition-all duration-500"
                  style={{ width: `${coveragePct}%` }}
                />
                <div
                  className="h-full bg-outline-variant"
                  style={{ width: `${100 - coveragePct}%` }}
                />
              </>
            )}
          </div>
        </div>

        {/* Legend */}
        <div className="grid grid-cols-2 gap-y-2">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-primary" />
            <span className="font-mono text-[9px] text-outline">ENABLED</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-outline-variant" />
            <span className="font-mono text-[9px] text-outline">DISABLED</span>
          </div>
        </div>
      </div>
    </section>
  );
}
