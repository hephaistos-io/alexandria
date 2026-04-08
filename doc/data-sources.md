# Data Sources in Alexandria

This document explains the data sources Alexandria pulls from, why they matter for conflict
analysis, and how the pipeline consumes each one. It is written for someone learning about
OSINT through this codebase.

---

## 1. What Is OSINT?

Open Source Intelligence (OSINT) is intelligence derived from publicly available sources:
news articles, government publications, academic datasets, social media, satellite imagery,
and more. "Open source" means the underlying data is accessible to anyone — it does not
require espionage, leaked documents, or proprietary access.

The term *intelligence* is the key distinction from raw *data*. A news article about an
airstrike is data. Knowing which country carried it out, cross-referencing it against
satellite imagery to confirm the location, correlating it with a week of prior diplomatic
signals, and assigning a confidence level to those conclusions — that is intelligence. The
transformation from data to intelligence requires aggregation, verification, disambiguation,
and analytical judgment.

Historically, this work was done manually by trained analysts reading reports and building
knowledge by hand. Automated pipelines change the economics of that work. A pipeline like
Alexandria can ingest thousands of events per day, extract entities, resolve ambiguities
against a structured knowledge base, and surface patterns that would take a human analyst
days to assemble. What automated systems cannot replicate (yet) is the judgment layer: the
ability to assess credibility, detect deception, and weigh conflicting accounts. That is
why Alexandria combines machine-processed data (GDELT) with human-curated data (UCDP, OSINT
geo-sources) — the two have complementary strengths.

---

## 2. GDELT — Global Database of Events, Language, and Tone

### What It Is

GDELT is a project maintained by Kalev Leetaru and Google Ideas (now Google Jigsaw). It
monitors news media worldwide — print, broadcast, and online — in over 100 languages, and
processes that coverage into a structured event database. It is, as of 2025, one of the
largest open databases of human society ever created.

The core insight behind GDELT is that news coverage is a proxy for real-world events. If a
newspaper in Nigeria reports that armed groups clashed near a border town, that report is
evidence that something happened. GDELT reads those reports at scale using automated natural
language processing and codes them into a structured format.

### CAMEO Event Codes

Every event in GDELT is tagged with a CAMEO code (Conflict and Mediation Event Observations).
CAMEO is a structured vocabulary for political events, organized as a hierarchy. Root codes
are broad categories; more specific sub-codes narrow the description.

Alexandria filters on a specific subset of CAMEO codes relevant to armed conflict:

| Root Code | Category         | Examples of Sub-Codes                        |
|-----------|------------------|----------------------------------------------|
| 18        | Assault          | Bombing (183), aerial weapons (195), assassination (186) |
| 19        | Fight            | Artillery fire (194), small arms (193), military blockade (191) |
| 20        | Mass Violence    | Mass killing (202), ethnic cleansing (203)  |
| Base 145  | Violent Protest  | Riots, violent demonstrations               |

One important filtering decision in `gdelt_fetcher/fetcher.py`: Alexandria does *not* use
GDELT's built-in `QuadClass == 4` (Material Conflict) filter, even though that is the
obvious choice. The reason is that QuadClass 4 also includes root code 17 (Coerce), which
covers arrests, curfews, and property seizure — events that are coercive but not armed
conflict. The fetcher applies a more precise filter directly on root and base codes.

### The Goldstein Scale

Each GDELT event is assigned a Goldstein scale value, a number between -10 and +10 that
represents the theoretical impact of the event type on political stability. Negative values
indicate destabilizing events; positive values indicate cooperative or stabilizing events.
Conflict events typically score in the -5 to -10 range. Assassinations score -10; ceasefires
score around +4.

The Goldstein scale is a property of the *event type*, not the specific event. Every
bombing in GDELT gets the same Goldstein score regardless of scale or casualties. This makes
it useful for broad classification but poor for assessing the actual severity of a specific
incident.

### How GDELT Works Mechanically

GDELT does not provide an API in the traditional sense. Instead, it publishes a new export
file every 15 minutes as a gzipped CSV inside a ZIP archive. The fetcher polls a
`lastupdate.txt` endpoint to discover the URL of the most recent export, downloads and
extracts the ZIP, then parses the TSV row by row.

The export files have no header row. Columns are strictly positional, as defined by the
GDELT 2.0 codebook. Alexandria maps column indices explicitly as named constants at the top
of the fetcher, for example `COL_ACTOR1_NAME = 6` and `COL_GOLDSTEIN_SCALE = 30`. This is
worth noting as a pattern: when working with a positional format where a column number is
the only documentation, naming the index as a constant is much more maintainable than
writing `row[30]` in the parsing logic.

Each row is a single event between two actors at a location. The fetcher extracts:
- The global event ID (used as a stable source ID for deduplication)
- Actor names (ACTOR1 and ACTOR2 — the parties involved)
- Event and root codes (CAMEO classification)
- Goldstein scale and source counts
- Geographic coordinates and a place name
- A source URL (the news article that triggered the coding)

GDELT resolves locations to coordinates using the GDELT Geographic Lookup Table. A known
artifact of this: GDELT uses `(0.0, 0.0)` to indicate "location unknown". The fetcher
explicitly drops events at that coordinate, since `(0.0, 0.0)` is a point in the Gulf of
Guinea off the coast of West Africa and would otherwise appear as a spurious event there.

### Strengths and Weaknesses

GDELT's primary strength is coverage and speed. It processes millions of articles per day
across hundreds of languages. No human-curated source can match that volume or the 15-minute
update cadence.

Its weakness is precision. GDELT is entirely machine-coded. NLP-based event extraction
makes mistakes — misidentifying actors, miscoding event types, double-counting the same
event from multiple news sources. A single real-world incident reported by 50 outlets can
produce 50 separate GDELT events. The `NUM_MENTIONS` and `NUM_SOURCES` columns partially
address this (higher values suggest a more widely-covered event), but deduplication remains
an unsolved problem at GDELT's scale.

The practical consequence: treat GDELT data as a high-recall, low-precision signal. It
will surface almost everything that happened, but with significant noise. It is most useful
for detecting that *something* is happening in a region, not for precisely characterizing
what happened.

---

## 3. UCDP — Uppsala Conflict Data Program

### What It Is

UCDP is a research program at Uppsala University in Sweden, operated by the Department of
Peace and Conflict Research. It has been collecting data on organized violence since 1946,
making it one of the most comprehensive and long-running conflict datasets in existence.

UCDP maintains several datasets. Alexandria uses the **GED Candidate Events** dataset,
accessed via the Candidate Events API. "Candidate events" are events that have been
identified as potential conflict incidents but may still be under review. The endpoint URL
in the codebase, `ucdpapi.pcr.uu.se/api/gedcandidate/26.0.2`, includes a version number
that reflects the dataset release year.

### How UCDP Differs from GDELT

The difference comes down to the production process:

| Dimension       | GDELT                          | UCDP                             |
|-----------------|--------------------------------|----------------------------------|
| Coding method   | Automated NLP                  | Human researchers                |
| Volume          | Thousands of events per day    | Hundreds of events per week      |
| Update cadence  | Every 15 minutes               | Weekly                           |
| Precision       | Low — significant noise        | High — reviewed and validated    |
| Temporal scope  | 1979 to present                | 1946 to present                  |
| Access          | No authentication required     | Requires an access token         |

The `UCDP_ACCESS_TOKEN` environment variable seen in `docker-compose.yml` is passed as the
`x-ucdp-access-token` request header. UCDP requires registration to get a token.

### What UCDP Provides

Each event in the UCDP API includes:

- **side_a / side_b**: the parties to the conflict (e.g., a government and an armed group)
- **type_of_violence**: coded as 1 (state-based), 2 (non-state), or 3 (one-sided violence)
- **best**: the best estimate of fatalities for this incident
- **date_start**: the date the event occurred
- **latitude / longitude**: georeferenced coordinates
- **where_description**: a textual description of the location
- **country**: the country where the event took place

The three violence types encode politically meaningful distinctions. State-based violence is
combat between a government and an armed opposition group. Non-state violence is armed
conflict between two non-government groups. One-sided violence is a deliberate attack on
civilians by any organized actor — which is why it is tracked separately, since it represents
a fundamentally different dynamic from combatant-on-combatant violence.

### UCDP's Role in Alexandria

Because UCDP is human-curated and precise, it anchors the conflict event dataset. When
GDELT and UCDP both record an event, the UCDP record is more reliable. The weekly cadence
means UCDP lags real-time events by days to weeks, but what it does record has been reviewed.
The fetch interval for UCDP in the deployment configuration is 604800 seconds — exactly
one week.

---

## 4. OSINT Geo-Sources

### What They Are

These are specialized open-source intelligence organizations that produce geolocated conflict
event data, usually focused on active conflict zones. Unlike GDELT (automated) or UCDP
(academic), these are communities of analysts — often volunteers — who use satellite imagery,
social media video verification, and local contacts to confirm and geolocate specific
incidents.

Alexandria uses the `osint-geo-extractor` Python library (imported as `geo_extractor`),
which aggregates data from five sources:

**Bellingcat** — A Netherlands-based investigative journalism outlet specializing in
open-source investigation and verification. Bellingcat pioneered many of the techniques
used in modern OSINT: geolocation from social media photos, satellite imagery analysis,
flight tracking. Their conflict event data focuses on incidents they have independently
verified.

**Texty** — A Ukrainian data journalism organization. Their conflict mapping focuses heavily
on the war in Ukraine, with a particular emphasis on documenting Russian military actions.

**GeoConfirmed** — A community-driven platform that maps conflict events using geolocated
social media evidence. Contributors submit events with source links; others independently
verify the coordinates.

**DefMon** — Focused on defense and military monitoring, particularly in the Ukraine
conflict. Tracks equipment losses, troop movements, and front-line changes using satellite
imagery and social media.

**CenInfoRes** — The Center for Information Resilience, a UK-based non-profit that maps
atrocities and human rights violations, particularly in Ukraine, Myanmar, and Syria. Their
work focuses on documentation for accountability purposes.

### The Synthetic ID Problem

Some sources (notably Texty) do not provide stable identifiers for events. Every time the
data is fetched, events arrive with `id=None`. This is a problem for deduplication: without
a stable ID, the pipeline cannot tell whether an event it is processing today is the same
one it processed yesterday.

Alexandria's solution is to generate a synthetic ID using SHA-256 hashing. The input to the
hash is a concatenation of the source name, latitude, longitude, date, and title:

```python
hash_input = f"{source_name}:{lat}:{lon}:{date}:{title}"
source_id = hashlib.sha256(hash_input.encode()).hexdigest()[:16]
```

SHA-256 is a cryptographic hash function — given the same inputs, it always produces the
same output. The output is truncated to 16 hex characters (64 bits of entropy), which is
more than sufficient to avoid accidental collisions in a dataset of this size. The important
property here is *determinism*: the same event will always produce the same synthetic ID
across multiple fetches, so the deduplication logic downstream treats it correctly.

The footgun to be aware of: if an event's title or coordinates are updated by the source
between fetches, the synthetic ID changes and the event appears as a new one. This is an
inherent limitation of deriving an ID from content rather than receiving one from the
source.

### Why These Sources Matter

Human-curated OSINT has a different quality profile from both GDELT and UCDP. It can cover
events that do not yet appear in news media (a social media video of an airstrike can be
geolocated before any journalist files a report), and it can be more granular (pinpointing
an incident to a specific street rather than a city). The trade-off is that coverage is
geographically uneven — these organizations tend to focus intensely on certain conflicts
(Ukraine, in particular) while covering others sparsely.

---

## 5. RSS/Atom News Feeds

### How RSS Works

RSS (Really Simple Syndication) is an XML-based format that news publishers use to announce
new content. A feed is a document at a stable URL that lists recent articles: title, link,
publication date, and a short summary. A reader (or in Alexandria's case, a service) polls
the feed URL at regular intervals, parses the XML, and processes any articles it has not
seen before.

Atom is a related format with a slightly different XML structure. The Python `feedparser`
library, which Alexandria uses, handles both RSS 2.0 and RSS 1.0 (RDF) transparently. The
application code does not need to know which format a given feed uses.

The polling model is worth understanding: there is no push mechanism in RSS. The service
must repeatedly ask "is there anything new?" Unlike a webhook or a message queue, if the
service is down during a burst of new articles, it catches up on the next poll cycle. RSS
was designed for low-frequency polling (hourly is typical); Alexandria polls BBC every 60
seconds, which is aggressive but within what public feeds tolerate.

### The Feeds Alexandria Monitors

| Origin            | Outlet             | Perspective                            | Interval |
|-------------------|--------------------|----------------------------------------|----------|
| `bbc_world`       | BBC World News     | UK, international                      | 60s      |
| `swissinfo`       | Swissinfo.ch       | Swiss/European, UN affairs             | 900s     |
| `un_news`         | UN News            | Multilateral, humanitarian             | 900s     |
| `aljazeera`       | Al Jazeera English | Middle Eastern, Global South           | 900s     |
| `the_diplomat`    | The Diplomat       | Asia-Pacific geopolitics               | 900s     |
| `global_voices`   | Global Voices      | Citizen journalism, underrepresented regions | 900s |
| `france24`        | France 24          | French-speaking Africa, European       | 900s     |
| `dw_world`        | Deutsche Welle     | German international, Africa, EU       | 900s     |
| `moscow_times`    | The Moscow Times   | Independent Russia coverage            | 900s     |

BBC runs at 60 seconds because it is the highest-volume feed and acts as an early warning
signal for breaking events. The rest run at 900 seconds (15 minutes), which is also the
GDELT export cadence — a convenient alignment.

The selection of sources is intentional. A pipeline that only consumed the BBC would have
systematic blind spots: UK and Western European coverage is strong, but Sub-Saharan Africa,
Central Asia, and Latin America are underrepresented. Al Jazeera provides a different lens
on the Middle East and Global South. The Diplomat covers Asia-Pacific security in depth.
The Moscow Times is an independent outlet that covers Russia from a non-Kremlin perspective
— important for conflict monitoring involving Russian actors. Global Voices aggregates
reporting from local bloggers and journalists in regions that rarely appear in Western media.

No collection of sources is neutral. Every outlet has a geographic focus, an editorial
perspective, and gaps. The goal is not to eliminate bias but to triangulate across enough
different perspectives that systematic gaps become visible.

### Deduplication

The same article can appear in a feed multiple times if the publisher edits it after
publication, or the same story can be picked up by multiple feeds. Alexandria handles this
with URL-based deduplication: once a URL has been processed, it is marked as seen and
skipped on subsequent polls.

Two backends handle the "seen URLs" state:

**RedisSeenUrls** — The production backend. Each URL is stored as a Redis key like
`seen:bbc_world:<url>` with a 7-day TTL. Individual keys expire independently, which avoids
the problem of a single key's TTL resetting the entire deduplication window. Redis
persistence means the seen-URLs set survives service restarts. It is also shared: if two
instances of the same fetcher are running, they share the same dedup state and do not
double-publish.

**InMemorySeenUrls** — The development fallback when Redis is not available. Backed by an
`OrderedDict` capped at 50,000 entries. When the cap is reached, the oldest entries are
evicted (FIFO). This is correct behavior for a bounded cache: evicting the oldest URLs means
very old articles can theoretically re-appear after eviction, but the downstream
article-store also deduplicates at the database level (URLs have a unique constraint), so
the worst outcome is a harmless rejected insert.

### URL Normalization

A subtle deduplication concern: Al Jazeera appends `?traffic_source=rss` to every article
URL in its feed. DW appends `?maca=en-rss-en-world-4025-rdf`. These are tracking parameters
with no semantic content. If the same article is encountered via the feed (with the
parameter) and later via a direct link (without it), they should be treated as the same URL.

Each source with this problem has a `clean_url` function that strips the tracking parameter
before the URL is used for deduplication or storage. The `RssFetcher` accepts this as a
`url_cleaner` callable, keeping the normalization logic in the source-specific module where
it belongs.

---

## 6. Wikidata as a Knowledge Base

### What Wikidata Is

Wikidata is the structured data layer behind Wikipedia, maintained by the Wikimedia
Foundation. Where Wikipedia stores information as natural language prose, Wikidata stores
it as machine-readable statements: facts about entities in the form of subject-property-value
triples. "Iran (Q794) — instance of (P31) — sovereign state (Q3624078)" is a typical
statement.

Every entity in Wikidata has a **QID** (Q-number): a stable, language-neutral identifier.
"Iran" is Q794 regardless of whether you search for it in English, Arabic, Persian, or
German. This language independence is crucial for OSINT, where sources report in many
languages and the same entity appears under different names.

### Properties Relevant to Alexandria

**P625 — coordinate location**: Geographic coordinates for an entity. Used by the
entity-resolver to attach latitude/longitude to location-type entities (countries, cities,
facilities). When a NER model identifies "Kyiv" as a GPE (geopolitical entity), the resolver
looks up Q1899 in Wikidata and retrieves P625 to get the coordinates.

**P31 — instance of**: What type of thing an entity is. The resolver uses this to filter
out Wikimedia-internal pages — categories, disambiguation pages, and list articles that are
administrative artifacts of Wikipedia, not real-world entities. A search for "Works" might
return "Category:Works by Indian people" (Q4167836 is a Wikimedia category QID); P31
filtering catches this and discards it.

### The Two Wikidata APIs

Wikidata has two distinct HTTP APIs, and it is worth understanding both because the
documentation and Stack Overflow answers often conflate them:

**The Action API** (`/w/api.php`) — the legacy API. It was built for MediaWiki's internal
use and exposes Wikidata functionality as an afterthought. It works, but the response
structures are deeply nested and inconsistent. Many older tutorials and libraries use this.

**The Wikibase REST API** (`/w/rest.php/wikibase/v1/`) — the newer API. Introduced around
2022-2023. Returns cleaner, more predictable JSON. Alexandria uses this exclusively:
- Search: `GET /wikibase/v1/search/items?q=...&language=en`
- Statements: `GET /wikibase/v1/entities/items/{QID}/statements?property=P625`

The REST API response for a search looks like:
```json
{
  "results": [
    {
      "id": "Q794",
      "display-label": {"value": "Iran"},
      "description": {"value": "country in Western Asia"}
    }
  ]
}
```

The nested `display-label` structure is slightly awkward but predictable. Compare to the
Action API's `wbsearchentities` response, which nests things differently and requires more
post-processing.

### Authentication and Rate Limits

Unauthenticated requests to Wikidata are limited to approximately 500 requests per hour.
With a personal API token or OAuth2 client credentials, this rises to 5,000 per hour.
Alexandria supports both authentication methods, with a fallback to unauthenticated access
if no credentials are configured.

The resolver also implements polite rate limiting: a 200ms delay between requests
(5 requests/second steady-state), and server-guided back-off on HTTP 429 responses. When
Wikidata returns a `Retry-After` header, the resolver sleeps for exactly that duration. This
is the correct approach: honor what the server asks for rather than guessing.

Results are cached in Redis with a 7-day TTL, keyed by entity mention and NER label. A
confirmed "not found" result is also cached (as a sentinel value `__NONE__`), so the same
unresolvable mention does not trigger repeated API calls.

### Why Wikidata Over Alternatives

**GeoNames** — A large geographic name database with coordinates. Strong for place names,
but covers only locations, not people, organizations, or events. Not suitable as a general
entity resolver.

**DBpedia** — Extracts structured data from Wikipedia infoboxes. An older project with a
similar goal to Wikidata. The data quality is inconsistent because infoboxes are maintained
separately from Wikidata statements, and the SPARQL endpoint has intermittent availability.
Wikidata is now the canonical structured data source for the Wikimedia ecosystem.

**OpenStreetMap / Nominatim** — Excellent for geographic geocoding (address to coordinates)
but not designed for resolving named entity mentions to structured knowledge graph entries.

Wikidata wins on breadth (it covers people, organizations, events, and places), stability
(QIDs are permanent identifiers), and active maintenance. Its main downsides are the rate
limits and the occasional quality issue on less-prominent entities.

---

## 7. NASA EONET — Earth Observatory Natural Event Tracker

### What It Is

EONET is a free, unauthenticated API operated by NASA's Earth Observatory that aggregates
natural-disaster events from a variety of NASA and partner sources — USGS for volcanoes and
earthquakes, InciWeb for US wildfires, national meteorological services for storms, and the
National Ice Center for sea and lake ice. It is the simplest piece of infrastructure in
Alexandria's ingest layer: one JSON endpoint, no auth, stable schema.

The event categories EONET covers include wildfires, severe storms, volcanoes, sea and lake
ice, drought, dust and haze, earthquakes, floods, landslides, manmade (industrial
accidents), snow, temperature extremes, and water color anomalies. Alexandria ingests all
categories without filtering — unlike GDELT, there is no noise to exclude, because EONET
events are hand-coded by domain specialists before they are published.

Natural disasters are not armed conflict, so it is reasonable to ask why they belong in an
OSINT platform aimed at conflict monitoring. Two reasons. First, disasters frequently
correlate with the events Alexandria already tracks: a drought precedes displacement, a
storm disrupts humanitarian corridors, a volcanic eruption triggers evacuations that
intersect with existing conflict zones. Second, the same dashboard that surfaces a wildfire
near a front-line position or a flood in a besieged city is more useful than one that only
shows the violence. The layer exists to provide geographic context for everything else.

### How the EONET API Works

A single HTTP GET returns all events for a configurable time window:

```
GET https://eonet.gsfc.nasa.gov/api/v3/events?status=all&days=30
```

Two query parameters matter. `status=all` includes both currently-open and recently-closed
events — without it, the API only returns open events, which hides wildfires that ended
yesterday or storms that dissipated last week. Those are still relevant for a "last 7 days"
dashboard view. `days=30` is a generous backfill window chosen because EONET events
routinely stay open for weeks (a multi-month wildfire season, a persistent sea-ice anomaly),
and the dashboard's 30-day range needs data on a fresh deployment.

The fetcher polls this endpoint every 1800 seconds (30 minutes). EONET updates on the order
of hours, not minutes, so a more aggressive interval would be wasted traffic.

### The Geometry Problem

Each EONET event has an array of **geometries**, not a single location. A wildfire spreading
over a week produces one geometry per daily observation; a tropical storm has a separate
geometry for every position report along its track. Geometries can be Points (single
coordinate), Polygons (an outer ring of vertices, like a wildfire perimeter or a sea-ice
extent), and occasionally other GeoJSON shapes.

This creates a modelling question: should one EONET event become many database rows (one
per geometry observation) or a single row (one per event)? Alexandria's v1 chooses
**one row per event**. The most recent geometry becomes the event's location, and all
earlier observations are discarded. The reasoning:

- A dashboard marker per daily wildfire observation would be N markers stacked on top of
  each other, which is visually indistinguishable from a single marker but costs N times
  the rendering work and N times the network payload.
- The v1 product surfaces *where a disaster is happening right now*, not *how it has
  migrated over time*. Historical trajectory is a v2 feature.
- A single stable identifier per event (the EONET ID) maps cleanly to one row with
  `ON CONFLICT DO NOTHING`, which is the same deduplication pattern used for articles and
  conflict events. Many-rows-per-event would require a separate strategy.

The tradeoff is that the time-series of a long-running event is lost. A wildfire that has
burned for two weeks shows up as a marker at its most recent position, not as a track.
Geometry timelines are a known v2 feature.

### Polygon Centroids

When the most recent geometry is a Polygon — a wildfire perimeter or a sea-ice boundary —
the fetcher reduces it to a single (lat, lng) marker by computing the **mean of vertices**
of the outer ring. This is a coordinate centroid, not the geographic centroid of the
enclosed area, and the two differ whenever the polygon's vertices are non-uniformly
distributed around its shape. For a convex roughly-round polygon they are nearly identical;
for a long thin polygon they can diverge.

The mean-of-vertices approach was chosen over a true centroid for two reasons. First, it
is a four-line loop with no dependencies — a proper GeoJSON centroid requires either Shapely
or hand-rolled geometry code that handles self-intersecting rings, holes, and edge cases.
Second, it is good enough for dropping a single marker on a map: a user clicking on an
irregular shape expects the marker somewhere inside it, and the coordinate mean is always
inside a convex hull of the vertices.

### The Longitude-Latitude Footgun

EONET follows GeoJSON, which orders coordinate pairs as **[longitude, latitude]**. This is
the opposite of the convention used by most other geographic APIs, most SQL databases, and
every tool that writes "lat, lng" in its documentation. The fetcher explicitly flips the
order on extraction with a comment noting the footgun — a silent bug here would produce
events that appear on the correct latitude but the wrong hemisphere, which is the kind of
error that takes hours to notice on a map because the markers *look* plausible.

### Categories

Each EONET event has a `categories` array of `{id, title}` objects. Most events have exactly
one category, but a few are tagged with multiple (a wildfire that triggers dust and haze
warnings). The fetcher comma-joins the category IDs into a single TEXT column on the
database side rather than introducing a junction table. The reasoning is pragmatic: a
junction table is the "correct" relational model, but nothing in Alexandria currently
queries disasters by category in a way that would benefit from a join. When the frontend
eventually introduces per-category sub-toggles (a v2 feature), the column can be promoted
to an array or a junction table without breaking the ingest path.

Events that arrive with no category at all are tagged `unknown` rather than dropped — the
category is metadata, and losing an entire event over a missing tag is more damaging than
carrying a placeholder.

### Event Timing

EONET exposes two temporal fields that map into Alexandria's schema:

- **`event_date`** — the timestamp of the most recent geometry observation, i.e. "when the
  disaster was last seen". This is *not* the event's start time; it is its latest update.
  For a storm reported daily over a week, `event_date` is the most recent report.
- **`closed_at`** — when EONET marked the event as no longer active (a wildfire contained,
  a storm dissipated). Null for open events.

The dashboard filters on `COALESCE(event_date, created_at)`, the same pattern used for
conflict events. If an event has a valid `event_date` it is filtered on that; if not (e.g.
a malformed EONET response with no geometry date), it falls back to the database ingest
time. This keeps the query correct for both well-formed and degraded data.

### Strengths and Weaknesses

EONET's strength is curation quality. Every event is reviewed before publication, and the
schema is stable enough that the fetcher has not needed defensive parsing beyond the
geometry-type handling described above. There is no equivalent of GDELT's noise floor.

Its weaknesses are coverage and latency. EONET is geared towards *globally notable* natural
events — a small local wildfire that burns an acre and is put out the same day will not
appear, whereas a week-long fire visible from orbit will. Storm tracks are reported on the
cadence of the source meteorological agency, which is often hours rather than minutes.
There is no "breaking news" latency profile; EONET is a curated list, not a real-time feed.

The other limitation is that EONET does not attempt to quantify severity in a uniform way.
The `magnitudeValue` and `magnitudeUnit` fields exist for categories where a numeric scale
makes sense (a wildfire's acres, a storm's wind speed), but are null for many events. The
schema carries them through but the dashboard does not yet use them for marker sizing —
that is a v2 concern.

---

## 8. Data Quality Challenges

Understanding where each source fails is as important as understanding what it provides.

### Noise in Automated Sources (GDELT)

GDELT's NLP-based coding has known error modes. The most common:

- **Duplicate events**: The same incident reported by many outlets generates many GDELT
  rows. The `NUM_MENTIONS` and `NUM_SOURCES` fields help, but there is no reliable
  single-event deduplication. Alexandria's approach is to store all events and let
  downstream analysis account for duplication.
- **Actor miscoding**: NLP frequently misidentifies who the actors are, particularly for
  ambiguous names, honorifics, or entities mentioned in passing.
- **Event code errors**: The difference between a "military blockade" (191) and "small arms
  fire" (193) matters analytically, but NLP systems trained on news text make systematic
  errors at this level of granularity.
- **Location errors**: GDELT's geo-resolution maps to country and city, but not to
  sub-national precision in many cases. In conflict monitoring, the difference between two
  towns 20km apart can be tactically significant.

### Gaps in Curated Sources (UCDP)

UCDP's human curation comes at the cost of coverage and latency:

- **Weekly lag**: Events coded this week reflect incidents from last week. For real-time
  alerting, UCDP is not useful. For historical analysis and trend detection, it is the
  gold standard.
- **Minimum threshold**: UCDP applies a minimum fatality threshold for inclusion. Events
  below that threshold are not recorded. This means low-casualty incidents — which may still
  be significant for understanding conflict dynamics — are systematically absent.
- **Geographic access**: Events in areas where independent reporting is restricted (North
  Korea, parts of Myanmar, closed conflict zones) are underrepresented regardless of how
  good the coding methodology is.

### Scraping Failures

The article-scraper service (which fetches full article text from URLs provided by the RSS
fetcher and GDELT) faces a category of problems that do not affect structured data sources:

- **Paywalls**: Many newspapers require subscriptions. The scraper receives an authentication
  challenge rather than article content.
- **Bot detection**: Some publishers block automated HTTP clients based on user-agent
  strings, request rates, or lack of JavaScript execution. A headless HTTP fetch looks
  different from a browser request.
- **Content delivery changes**: A URL that returns an article today may return a 404 next
  month if the publisher changes their URL structure.

### Entity Ambiguity

The entity-resolver faces the classic disambiguation problem: "Washington" can mean the US
state, the city, George Washington, or the Washington Post. Wikidata's search returns the
top result for a query, which is usually the most prominent entity by that name. For
well-known entities this works well. For names that are common across different entities,
the top result may be wrong.

The NER label (GPE, PERSON, ORG) helps narrow the search, but the resolver does not pass
the label to the Wikidata search query itself — it uses the label only to decide whether to
fetch P625 coordinates after the fact. A future improvement would be to incorporate the
label as a filter in the search request.

### Temporal Coverage Gaps

GDELT 2.0 coverage starts in 2015. UCDP GED Candidate events are a recent-vintage dataset
(the candidate pipeline began around 2018-2019, with the fuller GED dataset going back to
1989). The OSINT geo-sources have no systematic historical archive — they record events as
they happen. RSS feeds have no history beyond what is in the current feed at the time of
polling.

This matters for any analysis that requires a baseline. If you want to say "conflict in
this region has increased relative to the past five years," you need five years of data, and
the sources have different starting points and different event definitions. Cross-source
comparison requires careful accounting of these gaps.

---

## Summary

| Source          | Type           | Volume    | Cadence   | Quality  | Use in Alexandria                    |
|-----------------|----------------|-----------|-----------|----------|--------------------------------------|
| GDELT           | Automated NLP  | Very high | 15 min    | Noisy    | Real-time conflict event detection   |
| UCDP            | Human-curated  | Low       | Weekly    | High     | Authoritative conflict baseline      |
| OSINT Geo       | Human-OSINT    | Medium    | 3 hours   | Medium   | Verified geolocated incidents        |
| RSS Feeds       | News wire      | Medium    | 1-15 min  | Variable | Article text for NER/NLP pipeline    |
| Wikidata        | Knowledge base | N/A       | On-demand | High     | Entity disambiguation and linking    |
| NASA EONET      | Curated API    | Low       | 30 min    | High     | Natural-disaster context layer       |

Each source is wrong in its own way and right in its own way. The value of the pipeline is
not that any single source is definitive — it is that aggregating across sources with
different failure modes produces a more complete and more reliable picture than any one
source alone.
