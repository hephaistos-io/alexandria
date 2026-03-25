import { MaterialIcon } from "../shared/MaterialIcon";
import { useWikiSummary } from "../../hooks/useWikiSummary";

interface EntityPopupProps {
  qid: string;
  name: string;
  entityType: string;
  // Screen-space position (pixels) for the popup anchor point.
  screenX: number;
  screenY: number;
  entityTypeColor: (type: string) => string;
  onClose: () => void;
}

// Truncates a string to roughly `maxChars` characters at a word boundary.
function truncateExtract(text: string, maxChars = 280): string {
  if (text.length <= maxChars) return text;
  const truncated = text.slice(0, maxChars);
  const lastSpace = truncated.lastIndexOf(" ");
  return (lastSpace > 0 ? truncated.slice(0, lastSpace) : truncated) + "…";
}

// EntityPopup renders a floating card anchored to a graph node's screen
// position. It fetches the Wikipedia summary for the entity's QID and
// displays a thumbnail, name, type badge, QID, and extract.
//
// Positioning: absolute within the canvas container (position: relative).
// We offset the card up and to the right of the node dot so it doesn't
// obscure the node itself.
export function EntityPopup({
  qid,
  name,
  entityType,
  screenX,
  screenY,
  entityTypeColor,
  onClose,
}: EntityPopupProps) {
  const { summary, thumbnailUrl, source, loading } = useWikiSummary(qid);
  const color = entityTypeColor(entityType);

  // Popup dimensions — keep in sync with the w-[280px] class below.
  const POPUP_WIDTH = 280;
  const OFFSET_X = 12;
  const OFFSET_Y = -12;

  // Flip the popup to the left if it would overflow the right edge.
  // We can't know the container width here, so we check if the node
  // is far enough right that a right-anchored card makes sense.
  // This is a simple heuristic — good enough for a floating preview card.
  const left = screenX + OFFSET_X;
  const top = screenY + OFFSET_Y;

  const style: React.CSSProperties = {
    position: "absolute",
    left,
    top,
    transform: "translateY(-100%)",
    width: POPUP_WIDTH,
    // Border glow matching the entity type color
    boxShadow: `0 0 0 1px ${color}33, 0 8px 32px rgba(0,0,0,0.6), 0 0 20px ${color}18`,
    zIndex: 30,
  };

  return (
    <div
      style={style}
      className="bg-surface-container-high border border-outline-variant/20 overflow-hidden flex flex-col"
    >
      {/* Wikipedia thumbnail — shown at top if available */}
      {thumbnailUrl !== null && (
        <div className="w-full h-32 overflow-hidden shrink-0 relative">
          <img
            src={thumbnailUrl}
            alt={name}
            className="w-full h-full object-cover object-top"
          />
          {/* Subtle gradient to blend into the card body */}
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-surface-container-high/80" />
        </div>
      )}

      {/* Loading state for the thumbnail area */}
      {loading && thumbnailUrl === null && (
        <div className="w-full h-10 flex items-center justify-center bg-surface-container-highest shrink-0">
          <span className="font-mono text-[9px] text-outline uppercase tracking-widest">
            FETCHING...
          </span>
        </div>
      )}

      {/* Card body */}
      <div className="p-3 flex flex-col gap-2">
        {/* Header row: name + close button */}
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-headline font-black text-sm text-on-surface uppercase leading-tight flex-1">
            {name}
          </h3>
          <button
            onClick={onClose}
            className="text-outline hover:text-on-surface transition-colors shrink-0 mt-0.5"
            aria-label="Close popup"
          >
            <MaterialIcon name="close" className="text-sm" />
          </button>
        </div>

        {/* Metadata row: type badge + QID */}
        <div className="flex items-center gap-2">
          <span
            className="font-mono text-[9px] px-2 py-0.5 border"
            style={{
              color,
              borderColor: `${color}33`,
              backgroundColor: `${color}1a`,
            }}
          >
            {entityType}
          </span>
          <span className="font-mono text-[9px] text-tertiary">{qid}</span>
        </div>

        {/* Wikipedia extract */}
        {summary !== null && (
          <p className="text-[10px] text-on-surface-variant leading-relaxed font-mono">
            {truncateExtract(summary)}
          </p>
        )}

        {!loading && summary === null && (
          <p className="font-mono text-[9px] text-outline uppercase tracking-widest">
            NO_WIKI_SUMMARY
          </p>
        )}

        {/* Footer: Wikipedia attribution */}
        <div
          className="mt-1 pt-2 border-t font-mono text-[8px] text-outline uppercase tracking-widest"
          style={{ borderColor: `${color}22` }}
        >
          SRC: {source === "wikipedia" ? "WIKIPEDIA // EN" : source === "wikidata" ? "WIKIDATA" : "N/A"}
        </div>
      </div>
    </div>
  );
}
