export type AttributionFilter = "all" | "annotated" | "unannotated" | "auto_classified";
export type AttributionSort = "date_ingested" | "source_origin";

export interface EntityRoleType {
  id: number;
  name: string;
  description: string;
  color: string;
  enabled: boolean;
  created_at: string;
}

export interface CreateRoleTypePayload {
  name: string;
  description: string;
  color: string;
}

export interface UpdateRoleTypePayload {
  description?: string;
  color?: string;
  enabled?: boolean;
}

export interface AttributionEntity {
  text: string;
  label: string;
  canonical_name: string | null;
  wikidata_id: string | null;
  latitude: number | null;
  longitude: number | null;
  auto_role: string | null;
  auto_role_confidence: number | null;
}

export interface AttributionArticle {
  id: number;
  origin: string;
  title: string;
  summary: string | null;
  content: string;
  created_at: string;
  entities: AttributionEntity[] | null;
  manual_entity_roles: Record<string, string> | null;
  entity_roles_labelled_at: string | null;
}

export interface AttributionArticlePage {
  articles: AttributionArticle[];
  total: number;
  page: number;
  page_size: number;
}

export interface AttributionStats {
  total_with_entities: number;
  annotated_count: number;
  unannotated_count: number;
  progress_percent: number;
}
