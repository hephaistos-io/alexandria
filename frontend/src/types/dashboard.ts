export interface DashboardEntity {
  text: string;
  label: string;        // NER type: "GPE", "LOC", "FAC", "ORG", "PERSON", etc.
  wikidata_id: string | null;
  canonical_name: string | null;
  description: string | null;
  latitude: number | null;
  longitude: number | null;
  auto_role: string | null;
}

export interface DashboardArticle {
  id: number;
  url: string;
  source: string;
  origin: string;
  title: string;
  summary: string | null;
  published_at: string | null;
  created_at: string;
  manual_labels: string[] | null;
  automatic_labels: string[] | null;
  entities: DashboardEntity[] | null;
}
