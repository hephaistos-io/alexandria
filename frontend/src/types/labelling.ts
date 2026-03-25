export type FilterStatus = "all" | "labelled" | "unlabelled" | "auto_labelled";
export type SortField = "date_ingested" | "source_origin";

export interface ArticleSummary {
  id: number;
  origin: string;
  title: string;
  created_at: string;
  manual_labels: string[] | null;
  automatic_labels: string[] | null;
}

export interface ArticlePage {
  articles: ArticleSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface LabellingStats {
  total_count: number;
  labelled_count: number;
  unlabelled_count: number;
  classified_count: number | null;
  progress_percent: number;
}
