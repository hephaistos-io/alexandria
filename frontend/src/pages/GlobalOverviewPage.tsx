import { useMemo, useState } from "react";
import { GeoCanvas } from "../components/overview/GeoCanvas";
import { ScrapedFeedsPanel } from "../components/overview/ScrapedFeedsPanel";
import { SystemStatusFloat } from "../components/overview/SystemStatusFloat";
import { useDashboardArticles } from "../hooks/useDashboardArticles";
import { useEntityRoleTypes } from "../hooks/useEntityRoleTypes";
import { useInfraStatus } from "../hooks/useInfraStatus";
import type { DashboardArticle } from "../types/dashboard";
import type { GeoAnchor, SecondaryLocation } from "../types/pipeline";

// Spatial entity labels from the NER pipeline that carry coordinates.
// ORG and PERSON are excluded because they rarely resolve to a single point.
const GEO_LABELS = new Set(["GPE", "LOC", "FAC"]);

function pickPrimaryLocation(entities: DashboardArticle["entities"]) {
  if (!entities) return null;

  // Count how often each location entity text appears. The most frequently
  // mentioned location is usually the article's subject — e.g. "Israel" x7
  // beats "Arad" x2 in an article about Israeli missile strikes.
  const counts = new Map<string, { count: number; entity: (typeof entities)[number] }>();
  for (const e of entities) {
    if (!GEO_LABELS.has(e.label) || e.latitude == null || e.longitude == null) continue;
    const key = e.canonical_name ?? e.text;
    const existing = counts.get(key);
    if (existing) {
      existing.count++;
    } else {
      counts.set(key, { count: 1, entity: e });
    }
  }

  if (counts.size === 0) return null;

  // Pick the location with the highest mention count.
  let best: { count: number; entity: (typeof entities)[number] } | null = null;
  for (const entry of counts.values()) {
    if (!best || entry.count > best.count) best = entry;
  }
  return best!.entity;
}

// Collect all geo-located entities except the primary one. Each unique
// location (by canonical name) appears once — we don't need duplicates
// for drawing connection lines on the map.
function collectSecondaryLocations(
  entities: DashboardArticle["entities"],
  primaryKey: string,
  primaryCoords: [number, number],
): SecondaryLocation[] {
  if (!entities) return [];

  const seen = new Set<string>([primaryKey]);
  const locations: SecondaryLocation[] = [];

  for (const e of entities) {
    if (!GEO_LABELS.has(e.label) || e.latitude == null || e.longitude == null) continue;
    const key = e.canonical_name ?? e.text;
    if (seen.has(key)) continue;
    seen.add(key);

    // Skip locations that are too close to the primary — different entity
    // names can geocode to the same (or nearly the same) point, and drawing
    // a zero-length arc looks wrong. ~1° ≈ 111 km at the equator.
    const dLat = e.latitude - primaryCoords[0];
    const dLng = e.longitude - primaryCoords[1];
    if (Math.sqrt(dLat * dLat + dLng * dLng) < 1) continue;

    locations.push({
      name: key,
      coordinates: [e.latitude, e.longitude],
      role: e.auto_role ?? null,
    });
  }

  return locations;
}

function deriveAnchors(articles: DashboardArticle[]): GeoAnchor[] {
  return articles
    .map((article) => {
      const loc = pickPrimaryLocation(article.entities);

      if (!loc) return null;

      const primaryKey = loc.canonical_name ?? loc.text;

      const allLabels = [
        ...(article.automatic_labels ?? []),
        ...(article.manual_labels ?? []),
      ];

      return {
        id: String(article.id),
        city: primaryKey,
        label: article.title,
        category: allLabels[0] ?? "UNCLASSIFIED",
        summary: article.summary ?? "",
        source: article.origin,
        date: (article.published_at ?? article.created_at).split("T")[0],
        coordinates: [loc.latitude!, loc.longitude!] as [number, number],
        actionLabel: "VIEW_ARTICLE",
        labels: allLabels,
        secondaryLocations: collectSecondaryLocations(
          article.entities,
          primaryKey,
          [loc.latitude!, loc.longitude!],
        ),
      };
    })
    .filter((a): a is GeoAnchor => a !== null);
}

export function GlobalOverviewPage() {
  const { articles, loading } = useDashboardArticles();
  const { roleTypes } = useEntityRoleTypes();
  const { data: infraStatus } = useInfraStatus();
  const anchors = useMemo(() => deriveAnchors(articles), [articles]);
  const [selectedAnchorId, setSelectedAnchorId] = useState<string | null>(null);

  // Build a role name → hex color lookup from the user-defined role types.
  const roleColors = useMemo(() => {
    const map = new Map<string, string>();
    for (const rt of roleTypes) {
      map.set(rt.name, `#${rt.color.replace(/^#/, "")}`);
    }
    return map;
  }, [roleTypes]);

  const selectedAnchor = anchors.find((a) => a.id === selectedAnchorId) ?? null;

  // Clicking an article in the feed list selects its map marker (flyTo + arcs).
  // Clicking a map marker selects the article in the feed panel.
  function handleArticleClick(articleId: number) {
    const anchorId = String(articleId);
    // Toggle: clicking the same article deselects it.
    if (selectedAnchorId === anchorId) {
      setSelectedAnchorId(null);
    } else {
      setSelectedAnchorId(anchorId);
    }
  }

  function handleAnchorSelect(anchorId: string) {
    if (selectedAnchorId === anchorId) {
      setSelectedAnchorId(null);
    } else {
      setSelectedAnchorId(anchorId);
    }
  }

  return (
    <>
      <div className="flex h-full">
        <GeoCanvas
          anchors={anchors}
          focusedAnchorId={selectedAnchorId}
          selectedAnchorId={selectedAnchorId}
          onAnchorSelect={handleAnchorSelect}
          roleColors={roleColors}
        />
        <ScrapedFeedsPanel
          articles={articles}
          loading={loading}
          selectedAnchor={selectedAnchor}
          onArticleClick={handleArticleClick}
          onDismissSelection={() => setSelectedAnchorId(null)}
        />
      </div>
      <SystemStatusFloat status={infraStatus} />
    </>
  );
}
