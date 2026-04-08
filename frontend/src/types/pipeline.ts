// Types mirroring the Python pipeline dataclasses in src/alexandria/pipeline/

export interface Article {
  source: string;       // feed type: "rss", "api"
  origin: string;       // news outlet: "bbc_world", "ap"
  title: string;
  url: string;
  summary: string;
  published: string | null;  // ISO 8601 or null
  fetched_at: string;        // ISO 8601
}

export interface ScrapedArticle extends Article {
  content: string;
  scraped_at: string;
}

export interface TaggedMention {
  text: string;
  label: string;
  start_char: number;
  end_char: number;
}

export interface TaggedArticle extends ScrapedArticle {
  entities: TaggedMention[];
  tagged_at: string;
}

// Frontend-only types (no Python equivalent):

export interface SecondaryLocation {
  name: string;
  coordinates: [number, number];
  role: string | null;
}

export interface GeoAnchor {
  id: string;
  city: string;
  label: string;          // article title
  category: string;       // first topic label or "UNCLASSIFIED"
  summary: string;
  source: string;         // origin
  date: string;
  coordinates: [number, number];  // [latitude, longitude]
  actionLabel: string;
  labels: string[];       // all topic labels for display in popup
  secondaryLocations: SecondaryLocation[];  // other geo entities in the article
  // Optional disaster-specific extras. Only populated when this anchor was
  // derived from a NaturalDisaster (category === "NATURAL_DISASTER"). Stored
  // here rather than in a parallel lookup so the selection flow can render
  // the disaster detail card without an extra prop drill.
  magnitudeValue?: number | null;
  magnitudeUnit?: string | null;
  disasterCategory?: string;   // EONET category id (e.g. "wildfires")
  links?: string[];
  closedAt?: string | null;
  // Ordered sequence of observed positions (oldest → newest), already flipped
  // to [lat, lng] for Leaflet. Only set when the disaster has >=2 Point
  // observations — a single-point event has no track to draw. Used by
  // AnchorPoint to render a fading trail showing how the event has moved.
  track?: [number, number][];
}

export interface EventLogEntry {
  timestamp: string;      // "14:22:01.03"
  level: "info" | "success" | "warning" | "error" | "system";
  message: string;
  highlight?: string;
}

export interface DashboardMetrics {
  totalRecords: number;
  accuracyDelta: string;
  activeEndpoints: number;
  confidenceAvg: number;
  throughput: string;
  throughputPercent: number;
}

export interface IngestionBar {
  totalHeight: number;   // 0-100 percentage
  signalHeight: number;  // 0-100 percentage of total
  label?: string;
}
