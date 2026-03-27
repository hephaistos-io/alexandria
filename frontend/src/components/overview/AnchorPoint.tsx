import { divIcon } from "leaflet";
import { useRef, useState } from "react";
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
function buildIcon(isConflict: boolean) {
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
  const isConflict = anchor.category === "CONFLICT_EVENT";
  const iconRef = useRef(buildIcon(isConflict));
  const [hovered, setHovered] = useState(false);

  return (
    <>
      <Marker
        position={anchor.coordinates}
        icon={iconRef.current}
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
    </>
  );
}
