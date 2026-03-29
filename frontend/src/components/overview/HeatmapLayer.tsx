import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";

// leaflet.heat adds L.heatLayer as a side-effect import.
// The import itself registers the plugin with Leaflet's namespace.
import "leaflet.heat";

interface HeatmapLayerProps {
  /** Array of [lat, lng] points to render as a heatmap. */
  points: [number, number][];
  /** Whether the layer is currently visible. */
  visible?: boolean;
}

// Custom color gradient: transparent → amber → orange → red.
// The dark map base makes warm colours pop without needing high opacity.
const HEAT_GRADIENT: Record<number, string> = {
  0.0: "transparent",
  0.2: "rgba(255, 200, 50, 0.3)",
  0.4: "rgba(255, 160, 0, 0.5)",
  0.6: "rgba(255, 100, 0, 0.7)",
  0.8: "rgba(255, 50, 0, 0.85)",
  1.0: "rgba(220, 20, 20, 1)",
};

// Safely remove a heat layer from the map, guarding against the case where
// the Leaflet map instance has already been destroyed. leaflet.heat stores an
// internal `_map` reference; if it's null the map is gone and calling
// layer.remove() would throw "can't access property '_animating', this._map
// is null".
function safeRemove(layer: L.HeatLayer) {
  try {
    if ((layer as any)._map) {
      layer.remove();
    }
  } catch {
    // Map already destroyed — nothing to clean up.
  }
}

/**
 * Bridges leaflet.heat into react-leaflet.
 *
 * leaflet.heat is a plain Leaflet plugin, not a react-leaflet component. The
 * standard approach is to use useMap() (which gives us the raw L.Map instance)
 * and manage the heat layer imperatively via useEffect. This is the same
 * pattern react-leaflet's docs recommend for non-React Leaflet plugins.
 *
 * The layer is created once and reused — when `points` changes we call
 * setLatLngs() to update the data without destroying / recreating the canvas.
 */
export function HeatmapLayer({ points, visible = true }: HeatmapLayerProps) {
  const map = useMap();
  const layerRef = useRef<L.HeatLayer | null>(null);

  // Create the heat layer once on mount.
  useEffect(() => {
    const layer = L.heatLayer([], {
      radius: 20,
      blur: 25,
      maxZoom: 10,
      minOpacity: 0.15,
      gradient: HEAT_GRADIENT,
    });
    layerRef.current = layer;

    return () => {
      // Cleanup: remove from map when the component unmounts.
      // safeRemove guards against the map already being destroyed.
      safeRemove(layer);
      layerRef.current = null;
    };
  }, [map]);

  // Update point data whenever it changes.
  useEffect(() => {
    const layer = layerRef.current;
    if (!layer) return;
    // Guard: don't call setLatLngs if the layer has already been detached.
    if (!(layer as any)._map) return;
    layer.setLatLngs(points);
  }, [points, visible]);

  // Toggle visibility by adding/removing from the map.
  // addTo/remove are idempotent in Leaflet — calling addTo twice is safe.
  useEffect(() => {
    const layer = layerRef.current;
    if (!layer) return;

    if (visible) {
      // Only add if the map instance is still alive.
      if (map) {
        layer.addTo(map);
      }
    } else {
      safeRemove(layer);
    }
  }, [visible, map]);

  // This component renders nothing — the canvas layer is managed imperatively.
  return null;
}
