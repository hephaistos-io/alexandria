import { useEffect } from "react";
import { divIcon, type LatLngBoundsExpression } from "leaflet";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import MarkerClusterGroup from "react-leaflet-cluster";
import { AnchorPoint } from "./AnchorPoint";
import { HeatmapLayer } from "./HeatmapLayer";
import { LayerToggle, type LayerVisibility } from "./LayerToggle";
import type { GeoAnchor } from "../../types/pipeline";

// We need the default markercluster CSS for spiderfy animations, then
// override the visual style in index.css to match our dark tactical theme.
import "leaflet.markercluster/dist/MarkerCluster.css";

// Constrain panning to the visible world. Tight bounds prevent the user
// from dragging past the tile edge and exposing the page behind the map.
const WORLD_BOUNDS: LatLngBoundsExpression = [
  [-85, -180],
  [85, 180],
];

// CartoDB Dark Matter — a dark, minimal map tile designed for data overlays.
// The {r} token inserts "@2x" on retina screens for crisp tiles.
const TILE_URL =
  "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";

const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';

// MapController lives inside <MapContainer> so it can call useMap().
// react-leaflet requires useMap() to be called from a child of MapContainer —
// you cannot call it from the component that renders MapContainer itself.
// This component renders nothing; it only imperatively controls the map.
function MapController({ focusedAnchorId, anchors }: { focusedAnchorId: string | null; anchors: GeoAnchor[] }) {
  const map = useMap();

  // On mount, compute the zoom level that makes the full 360° of longitude
  // fill the container width. At zoom z the world is 256 * 2^z pixels wide,
  // so we need the smallest z where that exceeds the container width.
  // We also lock minZoom to this value so the user can never zoom out far
  // enough to see the edge of the tile layer.
  useEffect(() => {
    const containerWidth = map.getSize().x;
    const zoom = Math.ceil(Math.log2(containerWidth / 256));
    map.setMinZoom(zoom);
    map.setView([20, 0], zoom, { animate: false });
  }, [map]);

  // When an anchor is selected, pan to it without changing zoom level.
  useEffect(() => {
    if (!focusedAnchorId) return;
    const anchor = anchors.find((a) => a.id === focusedAnchorId);
    if (anchor) {
      map.panTo(anchor.coordinates, { duration: 0.8 });
    }
  }, [focusedAnchorId, anchors, map]);

  return null;
}

interface GeoCanvasProps {
  anchors: GeoAnchor[];
  focusedAnchorId?: string | null;
  selectedAnchorId?: string | null;
  onAnchorSelect?: (anchorId: string) => void;
  roleColors?: Map<string, string>;
  /** Coordinates for the conflict heatmap layer: [lat, lng][] */
  heatmapPoints?: [number, number][];
  /** Which layers are currently visible */
  layers: LayerVisibility;
  /** Callback when the user toggles a layer */
  onLayersChange: (layers: LayerVisibility) => void;
}

export function GeoCanvas({ anchors, focusedAnchorId = null, selectedAnchorId = null, onAnchorSelect, roleColors, heatmapPoints = [], layers, onLayersChange }: GeoCanvasProps) {
  // Filter anchors based on layer visibility. Each anchor is either an article
  // or a conflict event — we check the category to decide which toggle applies.
  const visibleAnchors = anchors.filter((a) => {
    if (a.category === "CONFLICT_EVENT") return layers.conflicts;
    if (a.category === "DETECTED_EVENT") return layers.events;
    return layers.articles;
  });
  return (
    // The outer div is position:relative so all the overlay chrome (crosshairs,
    // readouts, gradient) can be absolutely positioned on top of the map.
    <div className="relative flex-1 overflow-hidden bg-[#1a1a2e]">
      {/*
        MapContainer is the root Leaflet component. It must have an explicit
        height — "100%" works here because the parent flex container gives it
        a defined height via flex-1.

        center: initial map center [lat, lng] — roughly centered on the Atlantic
        to keep anchors visible at the default zoom level.
        zoom: 2 is the smallest zoom that shows the full world on a wide screen.
        zoomControl: false — we add our own or accept no controls for the
        tactical aesthetic. Setting to true keeps the default top-left zoom buttons.
      */}
      <MapContainer
        center={[20, 0]}
        zoom={2}
        minZoom={1}
        style={{ height: "100%", width: "100%" }}
        zoomControl={true}
        scrollWheelZoom={true}
        // Constrain panning — prevents scrolling into empty grey space
        // both horizontally (no duplicate world copies) and vertically.
        maxBounds={WORLD_BOUNDS}
        maxBoundsViscosity={1.0}
      >
        <TileLayer url={TILE_URL} attribution={TILE_ATTRIBUTION} noWrap />
        <MapController focusedAnchorId={focusedAnchorId} anchors={anchors} />

        {/* Heatmap canvas layer — rendered below markers so dots sit on top.
            leaflet.heat draws onto a <canvas> element which Leaflet composites
            at the tile-layer z-index. Markers live in a higher pane. */}
        <HeatmapLayer points={heatmapPoints} visible={layers.heatmap} />

        {/* MarkerClusterGroup merges nearby markers into count badges at
            low zoom. As the user zooms in past level 5, clusters break apart
            into individual markers. Spiderfy handles the case where markers
            overlap even at max zoom — clicking a cluster fans them out. */}
        <MarkerClusterGroup
          maxClusterRadius={60}
          spiderfyOnMaxZoom={true}
          spiderfyDistanceMultiplier={2}
          showCoverageOnHover={false}
          zoomToBoundsOnClick={true}
          iconCreateFunction={(cluster) =>
            divIcon({
              className: "geo-cluster-icon",
              html: `<span class="geo-cluster-count">${cluster.getChildCount()}</span>`,
              iconSize: [36, 36],
              iconAnchor: [18, 18],
            })
          }
        >
          {visibleAnchors.map((anchor) => (
            <AnchorPoint key={anchor.id} anchor={anchor} selected={anchor.id === selectedAnchorId} onSelect={onAnchorSelect} roleColors={roleColors} />
          ))}
        </MarkerClusterGroup>
      </MapContainer>

      {/* Blueprint grid lines — sits on top of the map tiles */}
      <div className="grid-overlay absolute inset-0 pointer-events-none z-[400]" />

      {/* Bottom gradient — fades the map into the surface colour so the
          transition to the feed panel below looks clean */}
      <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-surface to-transparent pointer-events-none z-[400]" />

      {/* Corner crosshair accents — four L-shaped border fragments */}
      <div className="absolute top-4 left-4 w-6 h-6 border-l border-t border-outline-variant/30 pointer-events-none z-[400]" />
      <div className="absolute top-4 right-4 w-6 h-6 border-r border-t border-outline-variant/30 pointer-events-none z-[400]" />
      <div className="absolute bottom-4 left-4 w-6 h-6 border-l border-b border-outline-variant/30 pointer-events-none z-[400]" />
      <div className="absolute bottom-4 right-4 w-6 h-6 border-r border-b border-outline-variant/30 pointer-events-none z-[400]" />

      {/* Top-left coordinate readout */}
      <div className="absolute top-6 left-8 font-mono text-[10px] text-outline/60 leading-relaxed pointer-events-none z-[400]">
        LAT: 20.0000 // LNG: 0.0000
      </div>

      {/* Layer visibility toggles */}
      <LayerToggle layers={layers} onChange={onLayersChange} />

      {/* Bottom-right telemetry readout */}
      <div className="absolute bottom-8 right-8 font-mono text-[10px] text-outline/60 text-right leading-relaxed pointer-events-none z-[400]">
        FRAME_RATE: 60FPS // ENCRYPTION: AES-256
      </div>

      {/* Role color legend */}
      {roleColors && roleColors.size > 0 && (
        <div className="absolute top-6 right-8 font-mono text-[10px] text-outline/60 pointer-events-none z-[400]">
          <p className="uppercase tracking-widest mb-1.5">ROLE_LEGEND</p>
          <div className="flex flex-col gap-1">
            {[...roleColors.entries()].map(([name, color]) => (
              <div key={name} className="flex items-center gap-2">
                <div className="w-4 h-[2px] shrink-0" style={{ backgroundColor: color }} />
                <span className="uppercase">{name}</span>
              </div>
            ))}
            <div className="flex items-center gap-2">
              <div className="w-4 h-[2px] shrink-0" style={{ backgroundColor: "#8ecae6" }} />
              <span className="uppercase text-outline/40">UNASSIGNED</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
