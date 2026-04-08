/**
 * One observation in a disaster's geometry timeline. EONET returns these as
 * an ordered array per event — a hurricane gets one entry every 6 hours, a
 * wildfire one entry per daily perimeter scan, etc.
 *
 * We store the entire array verbatim in the `geometries` JSONB column so the
 * frontend can render storm tracks and fire growth without a backend change.
 */
export interface DisasterGeometry {
  date: string;                       // ISO 8601
  type: "Point" | "Polygon";
  coordinates: number[] | number[][][]; // GeoJSON shape: Point=[lng,lat], Polygon=[[[lng,lat]...]]
  magnitudeValue?: number;            // optional, varies by category
  magnitudeUnit?: string;             // "kts", "acres", "hectare", "NM^2", ...
}

export interface NaturalDisaster {
  id: number;
  source_id: string;
  source: string;
  title: string;
  description: string | null;
  category: string;
  latitude: number;
  longitude: number;
  geometry_type: "Point" | "Polygon";
  event_date: string | null;
  closed_at: string | null;
  /** Magnitude of the LATEST observation — copied from the latest geometry. */
  magnitude_value: number | null;
  magnitude_unit: string | null;
  links: string[];
  /** Full EONET geometry timeline; oldest first. Empty array if none. */
  geometries: DisasterGeometry[];
  created_at: string;
}
