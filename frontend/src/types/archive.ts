import type { DashboardEntity } from "./dashboard";

export interface ArchiveArticle {
  id: number;
  origin: string;
  title: string;
  summary: string | null;
  published_at: string | null;
  created_at: string;
  manual_labels: string[] | null;
  automatic_labels: string[] | null;
}

export interface ArchivePage {
  articles: ArchiveArticle[];
  total: number;
  page: number;
  page_size: number;
}

export interface ArticleDetail {
  id: number;
  url: string;
  source: string;
  origin: string;
  title: string;
  summary: string | null;
  content: string;
  published_at: string | null;
  created_at: string;
  fetched_at: string;
  scraped_at: string;
  manual_labels: string[] | null;
  automatic_labels: string[] | null;
  entities: DashboardEntity[] | null;
}
