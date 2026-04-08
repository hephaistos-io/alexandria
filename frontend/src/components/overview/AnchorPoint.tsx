import { divIcon } from "leaflet";
import { useMemo, useState } from "react";
import { Marker, Polyline } from "react-leaflet";
import type { GeoAnchor } from "../../types/pipeline";

interface AnchorPointProps {
  anchor: GeoAnchor;
  selected?: boolean;
  onSelect?: (anchorId: string) => void;
  roleColors?: Map<string, string>;
}

// Default line color when no role is assigned or the role has no configured color.
const DEFAULT_LINE_COLOR = "#8ecae6";

// Visual size envelope for disaster markers. The dot scales with the event's
// magnitude (fire area, storm wind speed, etc.) so a Cat 5 hurricane and a
// 50-acre brush fire don't look identical. The ring is always 2x the dot.
const DISASTER_DOT_MIN = 8;
const DISASTER_DOT_MAX = 28;
const DISASTER_DOT_DEFAULT = 12;

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

/**
 * Map a disaster's magnitude to a marker dot diameter (px).
 *
 * EONET reports magnitudes in unit-specific scales:
 *   - "kts"     wind speed for severe storms (Saffir-Simpson 25 → 157+)
 *   - "acres"   fire size for wildfires (1 → 1,000,000+, log-scaled)
 *   - "hectare" same as acres but in metric (1 ha ≈ 2.47 ac)
 *   - "NM^2"    sea/lake ice extent in square nautical miles (log-scaled)
 *
 * Categories without magnitudes (floods, volcanoes) get the default size.
 */
function disasterDotSize(value: number | null | undefined, unit: string | null | undefined): number {
  if (value == null || unit == null) return DISASTER_DOT_DEFAULT;

  if (unit === "kts") {
    // Linear over the Saffir-Simpson range. 25kt is the lower bound for
    // tropical depressions; 157kt+ is Category 5.
    const t = (value - 25) / (157 - 25);
    return clamp(DISASTER_DOT_MIN + t * (DISASTER_DOT_MAX - DISASTER_DOT_MIN), DISASTER_DOT_MIN, DISASTER_DOT_MAX);
  }

  if (unit === "acres" || unit === "hectare") {
    // Wildfires span 6 orders of magnitude, so log-scale. Convert hectare
    // to acres so both units share one curve. log10(1) = 0 maps to MIN,
    // log10(1,000,000) = 6 maps to MAX.
    const acres = unit === "hectare" ? value * 2.47105 : value;
    const t = Math.log10(acres + 1) / 6;
    return clamp(DISASTER_DOT_MIN + t * (DISASTER_DOT_MAX - DISASTER_DOT_MIN), DISASTER_DOT_MIN, DISASTER_DOT_MAX);
  }

  if (unit === "NM^2") {
    // Sea ice extent — log-scaled, 1 → 100,000 NM² roughly. Less critical
    // visually so a slightly tighter envelope.
    const t = Math.log10(value + 1) / 5;
    return clamp(DISASTER_DOT_MIN + t * (DISASTER_DOT_MAX - 2 - DISASTER_DOT_MIN), DISASTER_DOT_MIN, DISASTER_DOT_MAX - 2);
  }

  // Unknown unit — fall back to default size.
  return DISASTER_DOT_DEFAULT;
}

// Generate points along a quadratic bezier curve between two coordinates.
// The control point is offset perpendicular to the straight line, which
// creates the arc effect. `segments` controls smoothness (more = smoother).
function curvedArc(
  start: [number, number],
  end: [number, number],
  segments = 40,
): [number, number][] {
  const [lat1, lng1] = start;
  const [lat2, lng2] = end;

  // Direction vector and its length
  const dLat = lat2 - lat1;
  const dLng = lng2 - lng1;
  const dist = Math.sqrt(dLat * dLat + dLng * dLng);

  if (dist === 0) return [start, end];

  // Midpoint of the straight line
  const midLat = (lat1 + lat2) / 2;
  const midLng = (lng1 + lng2) / 2;

  // Control point: offset the midpoint perpendicular to the line.
  // The offset magnitude scales with distance so short lines get subtle
  // curves and long lines get more visible arcs.
  const offset = dist * 0.25;
  const ctrlLat = midLat + (-dLng / dist) * offset;
  const ctrlLng = midLng + (dLat / dist) * offset;

  // Quadratic bezier: B(t) = (1-t)²·P0 + 2(1-t)t·C + t²·P1
  const points: [number, number][] = [];
  for (let i = 0; i <= segments; i++) {
    const t = i / segments;
    const u = 1 - t;
    points.push([
      u * u * lat1 + 2 * u * t * ctrlLat + t * t * lat2,
      u * u * lng1 + 2 * u * t * ctrlLng + t * t * lng2,
    ]);
  }

  return points;
}

// Build the custom DivIcon HTML once per anchor outside the render path.
// Leaflet's DivIcon lets us inject arbitrary HTML into the map canvas layer,
// which is how we get the pulsing ring + dot without fighting Leaflet's default
// icon system (which expects PNG images).
function buildIcon(
  category: string,
  magnitudeValue?: number | null,
  magnitudeUnit?: string | null,
) {
  if (category === "NATURAL_DISASTER") {
    // Disaster markers scale with the event's magnitude (fire size, wind
    // speed, ice area). The CSS classes provide colour + animation; inline
    // styles override the dimensions per-anchor.
    const dot = disasterDotSize(magnitudeValue, magnitudeUnit);
    const ring = dot * 2;
    return divIcon({
      className: "geo-anchor-marker",
      iconSize: [0, 0],
      iconAnchor: [0, 0],
      html: `
        <div class="geo-disaster-ring" style="width:${ring}px;height:${ring}px;"></div>
        <div class="geo-disaster-dot" style="width:${dot}px;height:${dot}px;"></div>
      `,
    });
  }
  if (category === "DETECTED_EVENT") {
    // Events get a larger, purple marker to distinguish them from individual
    // articles and conflict dots.
    return divIcon({
      className: "geo-anchor-marker",
      iconSize: [0, 0],
      iconAnchor: [0, 0],
      html: `
        <div class="geo-event-ring"></div>
        <div class="geo-event-dot"></div>
      `,
    });
  }
  const isConflict = category === "CONFLICT_EVENT";
  const ringClass = isConflict ? "geo-conflict-ring" : "geo-anchor-ring";
  const dotClass = isConflict ? "geo-conflict-dot" : "geo-anchor-dot";
  return divIcon({
    className: "geo-anchor-marker",
    // iconSize [0, 0] means Leaflet won't add any implicit sizing — our CSS
    // handles layout via absolute positioning relative to the coordinate point.
    iconSize: [0, 0],
    iconAnchor: [0, 0],
    html: `
      <div class="${ringClass}"></div>
      <div class="${dotClass}"></div>
    `,
  });
}

// The icon is static per marker — we build it once rather than on every render.
// useRef is React's escape hatch for values that persist across renders without
// causing re-renders themselves.
export function AnchorPoint({ anchor, selected = false, onSelect, roleColors }: AnchorPointProps) {
  const icon = useMemo(
    () => buildIcon(anchor.category, anchor.magnitudeValue, anchor.magnitudeUnit),
    [anchor.category, anchor.magnitudeValue, anchor.magnitudeUnit],
  );
  const [hovered, setHovered] = useState(false);

  // Prepare the disaster movement trail once per render so the map callback
  // below doesn't recompute `segments` on every iteration or reach for the
  // `anchor.track!` non-null assertion. `trackSegments` is either a ready-to-
  // render array of <Polyline> elements or null when the trail shouldn't show.
  const trackSegments = (() => {
    const track = anchor.track;
    if (!(selected || hovered) || !track || track.length < 2) return null;
    // `segments` is always >= 1 here because of the length check above.
    const segments = track.length - 1;
    return track.slice(0, -1).map((start, i) => {
      const end = track[i + 1];
      // t runs from ~0 (oldest segment) to ~1 (newest segment). We bias the
      // minimum up to 0.18 so the tail of the trail stays visible against
      // dark map tiles — pure 0 would disappear. The `segments === 1` guard
      // avoids a 0/0 NaN for tracks with exactly two vertices.
      const t = segments === 1 ? 1 : i / (segments - 1);
      const opacity = 0.18 + t * 0.72;
      // Slightly thicker line toward the present to reinforce direction.
      const weight = 1.5 + t * 1.0;
      return (
        <Polyline
          key={`track-${i}`}
          positions={[start, end]}
          pathOptions={{
            color: "#4ade80",
            weight,
            opacity,
            lineCap: "round",
          }}
        />
      );
    });
  })();

  return (
    <>
      <Marker
        position={anchor.coordinates}
        icon={icon}
        eventHandlers={{
          click: () => onSelect?.(anchor.id),
          mouseover: () => setHovered(true),
          mouseout: () => setHovered(false),
        }}
      />

      {/* Curved dashed connection lines to secondary locations.
          Shown on hover (quick preview) or when the marker is selected.
          Lines disappear when neither condition holds — keeps the map clean. */}
      {(selected || hovered) &&
        anchor.secondaryLocations.map((loc) => (
          <Polyline
            key={loc.name}
            positions={curvedArc(anchor.coordinates, loc.coordinates)}
            pathOptions={{
              color: (loc.role && roleColors?.get(loc.role)) || DEFAULT_LINE_COLOR,
              weight: 1.5,
              opacity: 0.6,
              dashArray: "6 4",      // 6px dash, 4px gap
              lineCap: "round",
            }}
          />
        ))}

      {/* Disaster movement track — a fading trail from oldest observation
          (faint) to the current marker position (bright). The direction of
          motion is implied by the opacity gradient: the trail fades into the
          past, and the bright end terminates at the main marker.

          Leaflet polylines have a single opacity value, so we render each
          segment as its own Polyline to get the gradient effect. A few extra
          DOM nodes per disaster is cheap, and the alternative (a plugin or a
          canvas overlay) is heavier than the gain. */}
      {trackSegments}
    </>
  );
}
