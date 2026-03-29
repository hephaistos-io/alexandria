import type { DashboardEntity } from "./dashboard";

export interface DetectedEvent {
  id: number;
  slug: string;
  title: string;
  status: "emerging" | "active" | "cooling" | "historical";
  heat: number;
  entity_qids: string[];
  centroid_lat: number | null;
  centroid_lng: number | null;
  first_seen: string;
  last_seen: string;
  article_count: number;
  conflict_count: number;
}

export interface EventArticle {
  id: number;
  title: string;
  source: string;
  url: string;
  summary: string | null;
  published_at: string | null;
  automatic_labels: string[] | null;
  entities: DashboardEntity[] | null;
}

export interface EventConflict {
  id: number;
  title: string;
  latitude: number;
  longitude: number;
  event_date: string | null;
  place_desc: string;
  source: string;
}

export interface DetectedEventDetail extends DetectedEvent {
  articles: EventArticle[];
  conflicts: EventConflict[];
}
