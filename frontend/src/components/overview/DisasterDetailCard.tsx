import type { GeoAnchor } from "../../types/pipeline";

interface DisasterDetailCardProps {
  anchor: GeoAnchor;
  onDismiss?: () => void;
}

/**
 * Format a magnitude value for display, with sensible unit handling.
 *
 * EONET reports magnitudes in raw numbers — this turns them into something
 * a human can read at a glance:
 *   - kts → "85 kts" (wind speed for storms)
 *   - acres → "12,500 ac" or "1.2M ac" depending on size
 *   - hectare → converted to acres for consistency with the rest of the UI
 *   - NM^2 → "150 NM²" (sea ice area)
 *
 * Returns null if there's no magnitude — the caller can branch on that to
 * hide the row entirely.
 */
function formatMagnitude(value: number | null | undefined, unit: string | null | undefined): string | null {
  if (value == null || unit == null) return null;

  if (unit === "kts") {
    return `${Math.round(value)} kts`;
  }
  if (unit === "acres" || unit === "hectare") {
    const acres = unit === "hectare" ? value * 2.47105 : value;
    if (acres >= 1_000_000) return `${(acres / 1_000_000).toFixed(1)}M ac`;
    if (acres >= 1_000) return `${(acres / 1_000).toFixed(1)}k ac`;
    return `${Math.round(acres)} ac`;
  }
  if (unit === "NM^2") {
    return `${Math.round(value)} NM²`;
  }
  return `${value} ${unit}`;
}

/**
 * Magnitude category badge — gives the user a qualitative sense of the
 * number alongside the raw value. Returns null if there's no useful tier.
 */
function magnitudeTier(value: number | null | undefined, unit: string | null | undefined): string | null {
  if (value == null || unit == null) return null;
  if (unit === "kts") {
    if (value >= 137) return "CAT_5";
    if (value >= 113) return "CAT_4";
    if (value >= 96) return "CAT_3";
    if (value >= 83) return "CAT_2";
    if (value >= 64) return "CAT_1";
    if (value >= 34) return "TROPICAL_STORM";
    return "TROPICAL_DEPRESSION";
  }
  if (unit === "acres" || unit === "hectare") {
    const acres = unit === "hectare" ? value * 2.47105 : value;
    if (acres >= 100_000) return "MEGAFIRE";
    if (acres >= 10_000) return "LARGE";
    if (acres >= 1_000) return "MODERATE";
    return "SMALL";
  }
  return null;
}

/**
 * Detail card for a selected NATURAL_DISASTER map marker.
 *
 * Mirrors ArticleDetailCard's tactical layout but surfaces disaster-specific
 * fields: EONET category, magnitude (with qualitative tier), source links,
 * closed/active status. Renders inside ScrapedFeedsPanel when the user
 * clicks a green disaster anchor on the map.
 */
export function DisasterDetailCard({ anchor, onDismiss }: DisasterDetailCardProps) {
  const magnitude = formatMagnitude(anchor.magnitudeValue, anchor.magnitudeUnit);
  const tier = magnitudeTier(anchor.magnitudeValue, anchor.magnitudeUnit);
  const isClosed = anchor.closedAt != null;

  return (
    <div className="shrink-0 border-b border-outline-variant/10 animate-[slideDown_150ms_ease-out]">
      {/* Section label — green to match the disaster layer colour */}
      <div className="px-4 pt-3 pb-1.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 bg-[#4ade80] shadow-[0_0_6px_#4ade80]" />
          <span className="font-mono text-[9px] text-[#4ade80] uppercase tracking-widest">
            SELECTED_DISASTER
          </span>
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="font-mono text-[9px] text-outline/50 hover:text-on-surface border border-outline-variant/30 hover:border-outline-variant/60 px-2 py-0.5 uppercase tracking-wider transition-colors"
          >
            RESET
          </button>
        )}
      </div>

      {/* Card body — green left border + faint green wash */}
      <div className="mx-3 mb-3 p-3 border-l-2 border-[#4ade80] bg-[#4ade80]/[0.06] shadow-[inset_0_0_20px_rgba(74,222,128,0.04)]">
        {/* EONET category + date */}
        <div className="flex justify-between items-start mb-2">
          <span className="font-mono text-[9px] text-[#4ade80] uppercase tracking-wider">
            {anchor.disasterCategory ?? "DISASTER"}
          </span>
          <span className="font-mono text-[10px] text-outline">
            {anchor.date}
          </span>
        </div>

        {/* Title */}
        <h4 className="font-headline text-sm font-bold text-on-surface mb-2">
          {anchor.label}
        </h4>

        {/* Magnitude row — only when present */}
        {magnitude && (
          <div className="flex items-center gap-2 mb-2">
            <span className="font-mono text-[9px] text-outline/50 uppercase tracking-widest">
              MAGNITUDE
            </span>
            <span className="font-mono text-[11px] text-on-surface font-bold">
              {magnitude}
            </span>
            {tier && (
              <span className="px-1.5 py-0.5 text-[8px] font-mono uppercase border border-[#4ade80]/40 text-[#4ade80]">
                {tier}
              </span>
            )}
          </div>
        )}

        {/* Status badge — closed events get a muted style */}
        <div className="mb-2">
          <span
            className={`px-1.5 py-0.5 text-[8px] font-mono uppercase border ${
              isClosed
                ? "border-outline/40 text-outline"
                : "border-[#4ade80]/60 text-[#4ade80]"
            }`}
          >
            {isClosed ? "CLOSED" : "ACTIVE"}
          </span>
        </div>

        {/* Description — EONET often returns null here, so guard the row */}
        {anchor.summary && (
          <p className="text-xs text-on-surface-variant leading-relaxed mb-3 line-clamp-4">
            {anchor.summary}
          </p>
        )}

        {/* Source link list — EONET event sources (InciWeb, JTWC, etc.).
            Each link is a small monospace pill that opens in a new tab. */}
        {anchor.links && anchor.links.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-3">
            {anchor.links.map((url) => {
              // Show just the host so the pill stays compact. Falls back to
              // the raw URL if parsing fails (defensive against malformed
              // URLs from upstream sources).
              let host = url;
              try {
                host = new URL(url).host.replace(/^www\./, "");
              } catch {
                /* keep raw url */
              }
              return (
                <a
                  key={url}
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-1.5 py-0.5 text-[8px] font-mono uppercase border border-[#4ade80]/30 text-[#4ade80] hover:border-[#4ade80]/60 transition-colors"
                >
                  {host}
                </a>
              );
            })}
          </div>
        )}

        {/* Footer — source attribution */}
        <div className="flex justify-between items-center">
          <span className="font-mono text-[9px] text-outline/50">
            SRC: {anchor.source.toUpperCase()}
          </span>
        </div>
      </div>
    </div>
  );
}
