import { useMemo, useState } from "react";
import { GeoCanvas } from "../components/overview/GeoCanvas";
import { ScrapedFeedsPanel } from "../components/overview/ScrapedFeedsPanel";
import { SystemStatusFloat } from "../components/overview/SystemStatusFloat";
import { useConflictEvents } from "../hooks/useConflictEvents";
import { useDashboardArticles } from "../hooks/useDashboardArticles";
import { useDetectedEvents } from "../hooks/useDetectedEvents";
import { useEntityRoleTypes } from "../hooks/useEntityRoleTypes";
import { useEventDetail } from "../hooks/useEventDetail";
import { useInfraStatus } from "../hooks/useInfraStatus";
import type { DashboardArticle } from "../types/dashboard";
import type { ConflictEvent } from "../types/conflict";
import type { DetectedEvent, EventArticle, EventConflict } from "../types/event";
import type { LayerVisibility } from "../components/overview/LayerToggle";
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

function deriveConflictAnchors(events: ConflictEvent[]): GeoAnchor[] {
  return events.map((e) => ({
    id: `conflict-${e.id}`,
    city: e.place_desc || "Unknown",
    label: e.title,
    category: "CONFLICT_EVENT",
    summary: e.description ?? "",
    source: e.source,
    date: e.event_date?.split("T")[0] ?? "",
    coordinates: [e.latitude, e.longitude] as [number, number],
    actionLabel: "VIEW_EVENT",
    labels: ["CONFLICT_EVENT"],
    secondaryLocations: [],
  }));
}

function deriveEventAnchors(events: DetectedEvent[]): GeoAnchor[] {
  return events
    .filter((e) => e.centroid_lat != null && e.centroid_lng != null)
    .map((e) => ({
      id: `event-${e.id}`,
      city: e.title,
      label: e.title,
      category: "DETECTED_EVENT",
      summary: `${e.article_count} articles, ${e.conflict_count} conflicts — ${e.status}`,
      source: "event-detector",
      date: e.last_seen.split("T")[0] ?? "",
      coordinates: [e.centroid_lat!, e.centroid_lng!] as [number, number],
      actionLabel: "VIEW_EVENT",
      labels: ["DETECTED_EVENT"],
      secondaryLocations: [],
    }));
}

// Convert EventArticle[] to DashboardArticle-shaped objects so we can pass
// them through the existing deriveAnchors function without duplicating the
// location-picking logic. EventArticle.source maps to DashboardArticle.origin
// (the display name of the outlet); source is left as an empty string since
// the detail endpoint doesn't expose the feed type.
function deriveEventArticleAnchors(articles: EventArticle[]): GeoAnchor[] {
  const adapted: DashboardArticle[] = articles.map((a) => ({
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
  }));
  return deriveAnchors(adapted);
}

function deriveEventConflictAnchors(conflicts: EventConflict[]): GeoAnchor[] {
  return conflicts.map((c) => ({
    id: `conflict-${c.id}`,
    city: c.place_desc || "Unknown",
    label: c.title,
    category: "CONFLICT_EVENT",
    summary: "",
    source: c.source,
    date: c.event_date?.split("T")[0] ?? "",
    coordinates: [c.latitude, c.longitude] as [number, number],
    actionLabel: "VIEW_EVENT",
    labels: ["CONFLICT_EVENT"],
    secondaryLocations: [],
  }));
}

const TIME_RANGES = [
  { key: "1h",  label: "1 HOUR",   ms: 60 * 60 * 1000 },
  { key: "6h",  label: "6 HOURS",  ms: 6 * 60 * 60 * 1000 },
  { key: "24h", label: "24 HOURS", ms: 24 * 60 * 60 * 1000 },
  { key: "7d",  label: "7 DAYS",   ms: 7 * 24 * 60 * 60 * 1000 },
  { key: "30d", label: "30 DAYS",  ms: 30 * 24 * 60 * 60 * 1000 },
] as const;

type TimeRangeKey = (typeof TIME_RANGES)[number]["key"];

export function GlobalOverviewPage() {
  const [timeRange, setTimeRange] = useState<TimeRangeKey>("24h");
  const rangeMs = useMemo(
    () => TIME_RANGES.find((r) => r.key === timeRange)!.ms,
    [timeRange],
  );
  const { articles, loading } = useDashboardArticles(rangeMs);
  const { events: conflictEvents } = useConflictEvents(rangeMs);
  const { events: detectedEvents } = useDetectedEvents(rangeMs);
  const { roleTypes } = useEntityRoleTypes();
  const { data: infraStatus } = useInfraStatus();
  const anchors = useMemo(() => deriveAnchors(articles), [articles]);
  const conflictAnchors = useMemo(() => deriveConflictAnchors(conflictEvents), [conflictEvents]);
  const eventAnchors = useMemo(() => deriveEventAnchors(detectedEvents), [detectedEvents]);
  const allAnchors = useMemo(
    () => [...anchors, ...conflictAnchors, ...eventAnchors],
    [anchors, conflictAnchors, eventAnchors],
  );
  const [selectedAnchorId, setSelectedAnchorId] = useState<string | null>(null);
  const [focusedEventId, setFocusedEventId] = useState<number | null>(null);
  const { detail: eventDetail, loading: eventDetailLoading } = useEventDetail(focusedEventId);

  // Layer toggle state — all layers visible by default.
  const [layers, setLayers] = useState<LayerVisibility>({
    articles: true,
    conflicts: true,
    heatmap: true,
    events: true,
  });

  // Extract [lat, lng] pairs for the heatmap. Memoized because the conflict
  // event list only changes on poll cycles (~60s), not on every render.
  const heatmapPoints = useMemo<[number, number][]>(
    () => conflictEvents.map((e) => [e.latitude, e.longitude]),
    [conflictEvents],
  );

  // Build a role name → hex color lookup from the user-defined role types.
  const roleColors = useMemo(() => {
    const map = new Map<string, string>();
    for (const rt of roleTypes) {
      map.set(rt.name, `#${rt.color.replace(/^#/, "")}`);
    }
    return map;
  }, [roleTypes]);

  const selectedAnchor = allAnchors.find((a) => a.id === selectedAnchorId) ?? null;

  // When focused on an event, narrow the map down to just that event's marker
  // plus the anchors derived from its related articles and conflicts.
  // When not focused, show the full combined anchor set.
  const displayAnchors = useMemo(() => {
    if (eventDetail) {
      const focusedEventAnchor = eventAnchors.find(
        (a) => a.id === `event-${focusedEventId}`,
      );
      const eventArticleAnchors = deriveEventArticleAnchors(eventDetail.articles);
      const eventConflictAnchors = deriveEventConflictAnchors(eventDetail.conflicts);
      return [
        ...(focusedEventAnchor ? [focusedEventAnchor] : []),
        ...eventArticleAnchors,
        ...eventConflictAnchors,
      ];
    }
    return allAnchors;
  }, [eventDetail, focusedEventId, eventAnchors, allAnchors]);

  // Same narrowing for the heatmap — only show conflict heat for the focused
  // event, so the heatmap reflects the same geographic scope as the markers.
  const displayHeatmap = useMemo<[number, number][]>(() => {
    if (eventDetail) {
      return eventDetail.conflicts.map((c) => [c.latitude, c.longitude]);
    }
    return heatmapPoints;
  }, [eventDetail, heatmapPoints]);

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
    if (anchorId.startsWith("event-")) {
      const numericId = parseInt(anchorId.slice("event-".length), 10);
      // Toggle: clicking the same event marker clears focus.
      if (focusedEventId === numericId) {
        setFocusedEventId(null);
        setSelectedAnchorId(null);
      } else {
        setFocusedEventId(numericId);
        setSelectedAnchorId(anchorId);
      }
    } else {
      // Clicking any non-event anchor clears event focus.
      setFocusedEventId(null);
      if (selectedAnchorId === anchorId) {
        setSelectedAnchorId(null);
      } else {
        setSelectedAnchorId(anchorId);
      }
    }
  }

  function handleClearFocus() {
    setFocusedEventId(null);
    setSelectedAnchorId(null);
  }

  return (
    <>
      <div className="flex h-full">
        <GeoCanvas
          anchors={displayAnchors}
          focusedAnchorId={selectedAnchorId}
          selectedAnchorId={selectedAnchorId}
          onAnchorSelect={handleAnchorSelect}
          roleColors={roleColors}
          heatmapPoints={displayHeatmap}
          layers={layers}
          onLayersChange={setLayers}
        />
        <ScrapedFeedsPanel
          articles={articles}
          loading={loading}
          selectedAnchor={selectedAnchor}
          onArticleClick={handleArticleClick}
          onDismissSelection={() => setSelectedAnchorId(null)}
          timeRange={timeRange}
          timeRanges={TIME_RANGES}
          onTimeRangeChange={setTimeRange}
          focusedEventId={focusedEventId}
          eventDetail={eventDetail}
          eventDetailLoading={eventDetailLoading}
          onClearFocus={handleClearFocus}
        />
      </div>
      <SystemStatusFloat status={infraStatus} />
    </>
  );
}
