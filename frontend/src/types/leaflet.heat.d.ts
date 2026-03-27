// Type declarations for leaflet.heat (no @types package available).
// leaflet.heat extends the L namespace with a heatLayer factory function.
// The actual class is L.HeatLayer but we only need the factory.
import * as L from "leaflet";

declare module "leaflet" {
  interface HeatLayerOptions {
    /** Minimum opacity (default 0.05) */
    minOpacity?: number;
    /** Maximum zoom at which points have full intensity (default 18) */
    maxZoom?: number;
    /** Radius of each point in pixels (default 25) */
    radius?: number;
    /** Amount of blur in pixels (default 15) */
    blur?: number;
    /** Maximum point intensity (default 1.0) */
    max?: number;
    /** Color gradient — keys are stops between 0 and 1 */
    gradient?: Record<number, string>;
  }

  interface HeatLayer extends L.Layer {
    setLatLngs(latlngs: Array<[number, number] | [number, number, number]>): this;
    addLatLng(latlng: [number, number] | [number, number, number]): this;
    setOptions(options: HeatLayerOptions): this;
    redraw(): this;
  }

  function heatLayer(
    latlngs: Array<[number, number] | [number, number, number]>,
    options?: HeatLayerOptions,
  ): HeatLayer;
}
