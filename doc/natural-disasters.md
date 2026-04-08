# Natural Disasters

A guide to how Alexandria ingests, stores, and displays natural-disaster events from NASA
EONET, and the design decisions behind keeping disasters as a separate layer from conflict
data.

This document complements `data-sources.md` (which explains what EONET is and how its API
works) and `pipeline-architecture.md` (which shows where the disaster pipeline fits in the
overall service graph). Read those first if you want the "what" before the "why".

---

## 1. Why a Separate Pipeline

Alexandria was originally an armed-conflict monitoring platform. Natural disasters are a
different kind of data: different provenance (satellites and meteorological agencies rather
than news reports and analysts), different schema (no actors, no casualties, no victim or
perpetrator roles), and different consumers in the UI (a context layer on the map, not a
driver of event detection).

The temptation when adding a new source is to reuse the existing schema and extend it. For
disasters, that would mean stuffing EONET events into `conflict_events` with some new
`type_of_violence` sentinel. This was rejected for three reasons.

**Schema mismatch.** Conflict events have `side_a`, `side_b`, `fatalities`, `type_of_violence`
— fields that do not apply to a wildfire. A disaster in the `conflict_events` table would
leave most columns null and introduce a new "is this a conflict or a disaster" discriminator
that every query would need to remember. That is worse than two tables with clean schemas.

**Query plan separation.** The dashboard's conflict query filters on event date and runs at
load time. Mixing disasters in would double the row count, force every conflict query to
add a `WHERE source != 'nasa_eonet'`, and degrade the index selectivity of
`idx_conflict_events_date`. A separate table with its own index (`idx_natural_disasters_date`)
keeps both query plans simple.

**Mirrors the existing split.** Alexandria already has `events` vs `conflict_events` as two
separate tables for two different kinds of "events" (named clusters from the detector vs
raw incidents from external sources). Adding `natural_disasters` as a third table fits the
precedent: each kind of event lives in the table with the schema that fits it.

The same logic applies to the message queue. `natural_disasters.raw` is a separate queue
from `conflict_events.raw` because the payload schemas differ, the two consumers can be
scaled and restarted independently, and adding a new disaster-specific consumer in the
future (e.g. a disaster-enrichment service) does not require touching the conflict pipeline.

---

## 2. The Fetcher

The `nasa-eonet-fetcher` service mirrors `ucdp-fetcher` almost line-for-line. That
symmetry is intentional: every periodic external-source fetcher in Alexandria uses the
same `SmartFetchLoop` pattern, the same Redis-backed dedup, and the same publish-to-AMQP
plumbing. A new fetcher is a copy-paste-and-rewrite-the-normalizer exercise, not a
reinvention.

The pieces that are EONET-specific are confined to `fetcher.py`:

- **`fetch()`** — a single `httpx.get` against the EONET v3 events endpoint. No pagination,
  no auth, no rate-limit back-off (EONET is a quiet API and 30-minute polling is far below
  any plausible threshold). HTTP errors are logged and the cycle returns an empty list;
  the next cycle will try again.
- **`_normalize()`** — converts one EONET event dict into a `NaturalDisaster` dataclass.
  Picks a representative marker position and magnitude from the latest geometry, joins
  category ids with commas, extracts source links, and passes the full geometry array
  through verbatim so downstream consumers can render the timeline.
- **`_latest_geometry()`** — sorts geometries by parsed date and returns the most recent
  one. Used to pick the marker position (the event's "current" location) and the
  representative magnitude (see below). Defensive against unordered input and against
  geometries with missing or unparseable dates (those sort to the bottom using
  `datetime.min` as a tz-aware sentinel).
- **`_extract_point()`** — handles `Point` and `Polygon` geometry types, flipping the
  GeoJSON `[lng, lat]` order to the `(lat, lng)` convention Alexandria uses everywhere
  else. Unknown geometry types (LineString, MultiPolygon) are skipped rather than
  half-handled. The comment in the code is explicit about the longitude-first footgun.

### Magnitude lives on the geometry, not the event

An early version of the fetcher read magnitude from `event["magnitudeValue"]` and every
disaster landed in the database with a null magnitude. The bug was silent because the API
response is valid JSON with that key present — just always `None`. EONET actually carries
magnitude on each individual geometry observation: a hurricane has 20 geometries and each
one has its own `magnitudeValue` (wind speed at that timestamp) and `magnitudeUnit`. The
event-level field is never populated.

The fix is to read magnitude from `_latest_geometry()` rather than from the event root, and
only when the value is non-null — otherwise the unit gets paired with a missing value. A
regression test in `tests/test_fetcher.py` pins the "latest geometry wins" behavior with
two dated observations, asserting the later date's magnitude is the one that ends up on
the dataclass. The takeaway for other fetchers: always look at a real API response before
assuming where each field lives, and write the test against the latest-observation
semantic rather than the first-observation semantic.

The surrounding `runner.py` is the generic `SmartFetchLoop`. Its "smart startup" behavior
is worth noting: on boot, it reads a Redis key `nasa_eonet_fetcher:last_fetch_ts` and, if
the previous run was less than one interval ago, sleeps for the remainder rather than
fetching immediately. This matters during rapid restarts (Docker Compose rebuilds,
Kubernetes rolling updates): without it, a service that is restarted every few minutes
would poll EONET every few minutes regardless of its configured interval. With it, the
effective polling rate is bounded by the interval even under restart pressure.

Deduplication happens in the loop, not the database. Each event's `source:source_id`
composite key (e.g. `nasa_eonet:EONET_1234`) is checked against a `SeenUrls` instance —
the same interface the RSS and conflict fetchers use — and only unseen events are
published. This avoids re-publishing events the fetcher has already delivered this process
lifetime. The database also enforces uniqueness via `ON CONFLICT (source, source_id) DO
NOTHING`, so duplicates are harmless but wasteful if they are not filtered at the fetcher.

---

## 3. The Consumer

`services/article-store/src/article_store/disaster_consumer.py` is a small module that
listens on `natural_disasters.raw` and writes each message into the `natural_disasters`
table. It is an entrypoint inside the existing `article-store` package, not a new service.
The reasoning is the same as `conflict_consumer`: both consumers are small, share the
`MessageConsumer` plumbing, share the Dockerfile and base image, and benefit from living
next to the schema they write to. Splitting them into separate repositories or separate
Python packages would add ceremony without buying anything.

The consumer runs as its own process — `docker-compose.yml` starts it under the service
name `disaster-store` with the command `python -m article_store.disaster_consumer`. That
gives it independent logging, independent restart policy, and independent scaling from the
article-store and conflict-store processes, even though the code lives in the same Python
package.

`DisasterWriter.save()` is the only non-trivial method. It issues a single parameterized
INSERT with `ON CONFLICT (source, source_id) DO NOTHING`, commits, and reports whether a
row was actually inserted (via `cur.rowcount`). This distinction matters for logging: the
happy path logs "Disaster stored" once per new event, and "Duplicate disaster skipped"
when the fetcher re-delivers an event across restarts. Without reporting the distinction,
the log would be ambiguous about whether ingest was working.

Two guards run before the INSERT:

1. **Required-field validation.** If `source_id`, `title`, `category`, `latitude`,
   `longitude`, `geometry_type`, or `fetched_at` is missing, the message is logged and
   dropped. This is defense-in-depth — the fetcher should never publish such a message,
   but a bad release or a direct-publish script could.
2. **(0, 0) rejection.** Like GDELT, any coordinate at the origin is rejected. For EONET
   this is less likely than for GDELT (EONET coordinates come from curated sources, not
   NLP geo-resolution), but the check costs nothing and prevents the Gulf-of-Guinea
   spurious-marker failure mode.

Both rejections simply return without ACKing anything special — the outer `MessageConsumer`
ACKs unconditionally in `finally` as described in `pipeline-architecture.md`, so malformed
messages are dropped rather than requeued into a poison loop.

---

## 4. The Schema

`SCHEMA_NATURAL_DISASTERS` in `services/article-store/src/article_store/schema.py` defines
the table:

```sql
CREATE TABLE IF NOT EXISTS natural_disasters (
    id              SERIAL PRIMARY KEY,
    source_id       TEXT NOT NULL,
    source          TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    category        TEXT NOT NULL,
    latitude        DOUBLE PRECISION NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    geometry_type   TEXT NOT NULL,
    event_date      TIMESTAMPTZ,
    closed_at       TIMESTAMPTZ,
    magnitude_value DOUBLE PRECISION,
    magnitude_unit  TEXT,
    links           TEXT[],
    geometries      JSONB NOT NULL DEFAULT '[]'::jsonb,
    fetched_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (source, source_id)
);
```

A few choices worth calling out:

**`source` as a column, not an implicit convention.** Every row records which upstream
source produced it. Today that is always `nasa_eonet`, but the column exists so that a
future disaster source (USGS earthquakes, GDACS, Copernicus EMS) can coexist in the same
table without a schema migration. The unique constraint is `(source, source_id)` rather
than just `source_id` for exactly this reason: two sources might independently use the
integer ID `1234`, and the composite key keeps them distinct.

**`links TEXT[]` instead of a junction table.** EONET events have 0–N source URLs. A
Postgres array column stores them inline, which is simpler to query, simpler to insert, and
fine for the small cardinality involved (typically 1–3 URLs per event). A junction table
would be the textbook answer, but textbook answers are not always the right answer: there
is no query in Alexandria that joins on a disaster's individual source URL, so the
overhead of a join table is unjustified.

**Both `event_date` and `created_at`.** `event_date` is when the disaster was observed
(from EONET's latest geometry); `created_at` is when the row landed in Postgres. They
differ — an event observed last week can land in the database today when the fetcher first
encounters it. The dashboard filters on `COALESCE(event_date, created_at)` so that
well-formed events sort by their real observation time but malformed events (missing
geometry date) still appear instead of vanishing.

**The index.** `idx_natural_disasters_date` is defined on `COALESCE(event_date, created_at)
DESC`. This is the exact column expression the dashboard query sorts and filters on, so
Postgres can use the index for both the `WHERE` and the `ORDER BY` in a single scan. The
same pattern is used for `conflict_events` and for `articles`.

**`geometries JSONB` instead of a child table.** Every EONET event carries an ordered
array of observation records — a hurricane has one every six hours for a week, an iceberg
has one every few days for years. The textbook answer is a `disaster_geometries` child
table with a foreign key, a `(disaster_id, observed_at)` index, and a join in every
query. The textbook answer is wrong here. The frontend needs the full array for every
disaster it renders, so every query would always fetch every child row — the join buys
nothing. And the array is never queried on its own (nobody asks "give me all geometry
observations between X and Y regardless of which disaster they belong to"). Storing the
array as JSONB on the parent row collapses the query plan to a single table scan, lets
`psycopg3` decode the column directly into a Python `list[dict]` without a `json.loads`
call, and keeps the schema small. The consumer wraps the payload with the
`psycopg.types.json.Jsonb` adapter on insert so the driver knows to pass it through as
`jsonb`, not as a Python dict embedded in a bytes string.

The v1 of this table did not have a `geometries` column — it stored only the latest
observation. The column was added when the frontend needed movement trails for hurricanes
and icebergs (see Section 6). That migration was destructive because no existing data was
worth preserving (the stored rows had always been single snapshots), so the local stack
was reset with `docker compose down --volumes` and the disasters were re-fetched fresh
from EONET. In a production deployment the equivalent change would be an additive
`ALTER TABLE … ADD COLUMN geometries JSONB NOT NULL DEFAULT '[]'::jsonb` followed by a
backfill pass — EONET is idempotent on `source_id`, so re-fetching is always safe.

---

## 5. The Dashboard API

The monitoring-api exposes disasters at `GET /api/dashboard/natural-disasters?since=<ISO>`.
The handler lives in `server.py`; the SQL lives in `disaster_client.py`. This split is
consistent with the rest of monitoring-api: the server layer handles HTTP, validation, and
error reporting, and the client layer owns the query and the row-to-dataclass mapping.

The query is a straight `SELECT … FROM natural_disasters WHERE COALESCE(event_date,
created_at) >= %s ORDER BY … DESC LIMIT 2000`. The 2000-row cap is a safety rail, not a
pagination mechanism — if a caller asks for the entire history the response is bounded,
and if 2000 rows is ever insufficient the answer is to add a proper pagination interface,
not to lift the cap. The dashboard's default `since` value is a few days, which produces
response sizes in the tens or low hundreds of rows in practice.

Results are serialized as `DashboardDisaster` dataclasses, with the timestamps converted
to ISO 8601 strings at the boundary. This matches the conflict-events endpoint — the
frontend never sees Python `datetime` objects, only strings.

---

## 6. The Frontend Layer

On the map, disasters are rendered as a dedicated layer that can be toggled on and off
independently from conflict events and article anchors.

### Plumbing

- `frontend/src/types/disaster.ts` defines the `NaturalDisaster` TypeScript interface,
  which mirrors the `DashboardDisaster` dataclass field-for-field. A nested
  `DisasterGeometry` interface describes one observation from the JSONB timeline.
- `frontend/src/hooks/useNaturalDisasters.ts` is the React hook that fetches the endpoint,
  mirroring `useConflictEvents` in shape (same polling pattern, same error handling, same
  cache semantics).
- `GlobalOverviewPage.tsx` merges the disaster results into the shared `allAnchors` array
  via `deriveDisasterAnchors`, so the same map rendering path handles conflicts,
  disasters, and article clusters.
- `LayerToggle.tsx` adds a `DISASTERS` toggle, colored green (`#4ade80`) to contrast with
  the red used for conflict events.

The toggle is intentionally single-grained. EONET has roughly a dozen categories
(wildfires, storms, volcanoes, sea ice, and so on), and a per-category sub-toggle system
would clutter the layer panel for what is currently a context layer. Per-category
sub-toggles are a v2 feature once we have telemetry on whether users want them.

### Magnitude-driven marker sizing

`AnchorPoint.tsx` has a `NATURAL_DISASTER` branch in `buildIcon()` that scales the dot
diameter with the disaster's magnitude. The default Cat-5 hurricane and a 50-acre brush
fire used to look identical, which wasted a whole channel of visual information. The
sizing function lives in `disasterDotSize()` and is per-unit:

| Unit | Scale | Reasoning |
|---|---|---|
| `kts` | Linear, 25 → 157 | The Saffir-Simpson scale is roughly linear and bounded, and the 25 kt floor is the lower threshold for tropical depressions. A single envelope handles the whole range. |
| `acres` / `hectare` | Logarithmic base-10, 1 → 1,000,000 | Wildfires span six orders of magnitude. A linear scale would make every fire look like either a dust speck or the whole state of California. Hectare values are converted to acres (`× 2.47105`) so both units share one curve. |
| `NM^2` | Logarithmic base-10, 1 → 100,000 | Sea-ice extents span several orders of magnitude but are less visually critical than fires and storms, so the envelope is tighter. |

Everything clamps into `[DISASTER_DOT_MIN, DISASTER_DOT_MAX]` so a runaway magnitude
(bad upstream data, a 10-million-acre number) cannot produce a dot that covers the
continent. Categories with no magnitude (floods, volcanoes in EONET's data) fall through
to a neutral default size.

The `divIcon` HTML uses inline `style="width:...;height:..."` overrides because the CSS
class (`.geo-disaster-dot`) cannot know the per-marker dimension. The dependency array on
the `useMemo` that builds the icon includes `magnitudeValue` and `magnitudeUnit` so the
icon rebuilds if the backing data changes.

### Movement track polylines

When the user hovers or selects a disaster marker, any disaster with two or more Point
observations in its `geometries` timeline gets a fading trail rendered from its oldest
position (faint) to its newest (bright, terminating at the main marker). The opacity
gradient implies the direction of motion: the trail fades into the past, and the bright
end is "now". This is the visual idiom tropical-cyclone tracking charts use, and it reads
intuitively even without a legend.

The track is derived in `GlobalOverviewPage.deriveDisasterTrack()`, which:

1. Short-circuits if there are fewer than two geometries (nothing to draw).
2. Sorts a copy of the geometries array by ISO 8601 date ascending. Lexicographic string
   sort is correct for ISO 8601 — one of the reasons the format is worth using everywhere.
3. Walks the sorted list, skipping any non-Point entries, flipping each
   `[lng, lat]` to `[lat, lng]`, and dropping entries whose coordinates are not valid
   numbers.
4. Returns the track only if at least two usable points survived; otherwise `undefined`
   so the renderer can branch on its presence.

`AnchorPoint.tsx` renders the trail as `track.length - 1` individual `<Polyline>`
segments rather than one polyline, because Leaflet polylines have a single opacity
value and a gradient would otherwise require a plugin or a canvas overlay. Each segment's
opacity and weight are interpolated along `t = i / (segments - 1)`:

- **Opacity:** `0.18 + t * 0.72` — oldest segment ~0.18 (faint but visible against the
  dark basemap), newest ~0.90 (bright).
- **Weight:** `1.5 + t * 1.0` — 1.5 px at the tail, 2.5 px at the head. The subtle
  thickening reinforces the arrow-of-time without looking garish.

The trail is only rendered on hover/select, matching the existing `secondaryLocations`
pattern and keeping the map clean when many disasters are visible at once. For EONET the
feature only lights up for severe storms and sea-ice events — wildfires, floods, and
volcanoes all arrive as single-observation snapshots and correctly show no trail.

### Disaster detail card

`frontend/src/components/overview/DisasterDetailCard.tsx` is the sidebar panel that
appears when a user clicks a disaster marker. It is the disaster-specific counterpart to
`ArticleDetailCard`; `ScrapedFeedsPanel` branches on `selectedAnchor.category ===
"NATURAL_DISASTER"` to choose between the two.

The card surfaces the fields EONET actually provides:

- **Category badge** (EONET category id, green).
- **Title and event date.**
- **Magnitude row**, formatted per-unit: `85 kts`, `12.5k ac`, `150 NM²`. A small tier
  badge next to the number gives a qualitative label — `CAT_5` / `CAT_4` / ... /
  `TROPICAL_DEPRESSION` for wind speeds, `MEGAFIRE` / `LARGE` / `MODERATE` / `SMALL` for
  burn areas. Both are computed in `formatMagnitude()` and `magnitudeTier()` helpers at
  the top of the file.
- **Status badge** — `ACTIVE` or `CLOSED`, keyed off whether `closed_at` is set.
- **Description**, if EONET provides one. Many events (particularly GDACS-sourced
  international wildfires) have `null` descriptions and the row is hidden entirely.
- **Source link pills** — one per URL in the `links` array. Each pill shows just the
  host (`www.` stripped) for compactness, falling back to the raw URL if `new URL()`
  throws. All links open in a new tab with `rel="noopener noreferrer"` so the opened
  page cannot navigate the parent window via `window.opener`.

The styling matches `ArticleDetailCard` at the structural level but uses the disaster
green (`#4ade80`) throughout — left border, section label, badge outlines, link pills.
This visually ties the card back to its marker and distinguishes disaster detail from
article detail at a glance.

---

## 7. What Disasters Are *Not* Wired Into

It is as important to understand what disasters deliberately *do not* interact with as
what they do.

**The heatmap.** Alexandria's article heatmap uses the density formula described in
`event-detection.md`:

```
heat = sqrt(articles) × max(1, conflicts^0.3) × exp(-0.01 × hours_since_last_article)
```

The formula is specifically about *armed-violence coverage density*. Mixing natural
disasters into the `conflicts` term would conflate two fundamentally different signals: a
hundred news articles about a wildfire would boost the heatmap in exactly the same way as
a hundred articles about a bombing, which is analytically wrong. Disasters live in their
own visual layer and do not alter the conflict heatmap in any way.

**Event detection.** The event-detector (`event-detection.md`) clusters articles and
correlates them with conflict events by country. It does not read from `natural_disasters`.
A named event in Alexandria is currently an armed-conflict event; fusing disasters into
the clustering would require rethinking what "event" means in the product. Disaster-aware
event fusion is a v2 feature.

**The NLP pipeline.** Disasters do not pass through `ner-tagger`, `entity-resolver`,
`role-classifier`, or `topic-tagger`. EONET already provides structured, curated metadata;
running NER over a disaster's one-sentence title would produce nothing the fetcher has not
already extracted, at significant cost.

Keeping these boundaries clean is what makes "add a new source" a tractable change. Each
time a new kind of data is introduced, the question is not "how does this interact with
every existing component?" but "which components should it interact with, and which should
stay untouched?" For disasters in v1 the answer is: ingest, store, API, map layer — and
nothing else.

---

## 8. Future Work

Everything still deferred, in rough order of how likely each is to become useful:

- **Per-category sub-toggles.** A dropdown or nested layer panel allowing the user to show
  only wildfires, only storms, etc. Requires promoting `category` from a joined TEXT to
  either a Postgres array or a junction table.
- **Animated track playback.** Turn the static movement trail into a scrubbable timeline
  where the user can replay how a hurricane or iceberg moved day-by-day. The data is
  already present in the `geometries` JSONB column — this is purely a UI feature on top of
  what the schema already stores.
- **Event-detector fusion.** Clustering articles, conflicts, and disasters into the same
  named-event graph. The hardest of these because it requires deciding what "event" means
  when the underlying data has different provenance and different temporal granularity.
- **NASA FIRMS integration for real wildfire visualization.** EONET's wildfire data is
  structurally limited: every wildfire event arrives as a single-point snapshot with a
  single magnitude reading, no perimeter, no growth history, no containment. The reason is
  that EONET aggregates from GDACS and IRWIN, both of which publish event metadata rather
  than fire behavior. To render fires the way Zoom.earth, Fire.ca.gov, or the NIFC map do
  (burn perimeters, hotspot clusters, spread animation) requires a different upstream.
  NASA FIRMS (Fire Information for Resource Management System) publishes near-real-time
  active-fire hotspot point clouds from the MODIS and VIIRS satellites. Adding a
  `firms-fetcher` service that writes to a new `fire_hotspots` table would let the map
  render a density layer of currently-burning pixels instead of one dot per GDACS alert.
  This is non-trivial: it is a density problem rather than an event problem, and the
  rendering path is closer to the conflict heatmap than to `AnchorPoint`.
- **Additional event sources.** USGS for earthquakes and volcanic alerts, GDACS direct for
  rapid impact assessments, Copernicus EMS for European emergency-management activations.
  The `source` column in `natural_disasters` is already designed to hold multiple values,
  so adding a new fetcher means writing a new normalizer and reusing the existing consumer.
