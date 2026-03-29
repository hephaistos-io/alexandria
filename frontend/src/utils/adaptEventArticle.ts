import type { DashboardArticle } from "../types/dashboard";
import type { EventArticle } from "../types/event";

/**
 * Maps EventArticle to the shape ArticleCard and deriveAnchors expect.
 *
 * EventArticle.source is the outlet display name, which corresponds to
 * DashboardArticle.origin. DashboardArticle.source (feed type) has no
 * equivalent here, so we default it to an empty string — ArticleCard
 * never renders it directly.
 */
export function adaptEventArticle(a: EventArticle): DashboardArticle {
  return {
    id: a.id,
    url: a.url,
    source: "",
    origin: a.source,
    title: a.title,
    summary: a.summary,
    published_at: a.published_at,
    created_at: a.published_at ?? "",
    manual_labels: null,
    automatic_labels: a.automatic_labels,
    entities: a.entities,
  };
}
