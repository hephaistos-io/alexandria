# Alexandria

An OSINT platform for gathering, ingesting, and analyzing open-source intelligence data. Named after the Library of Alexandria — the ambition is to collect and organize knowledge from diverse sources into a unified, queryable system.

Actively developed as a learning project for python, data pipelines, NLP. Built with AI coding assistants.

## Core Idea

- **Data Ingestion**: Pull data from multiple open sources (APIs, feeds, scraped content)
- **Processing Pipeline**: Clean, normalize, and enrich raw data into structured intelligence
- **On-Demand Model Training**: Fine-tune small ML models on collected data for domain-specific analysis (Only manual labelling is implemented, the training pipeline doesn't exist yet...)
- **Search & Analysis**: Query the knowledge base and surface patterns across sources

## Current Status

Active development — pipeline is functional end-to-end.


- **Data Ingestion**: Generic RSS scraper can be used for various sources that provide one
- **Conflict Data Ingestion**: Two independent fetcher services pull geolocated armed conflict events from OSINT sources (Bellingcat, Texty, etc.) and the UCDP Candidate Events API
- **Natural Disaster Ingestion**: A dedicated fetcher pulls geolocated natural events (wildfires, severe storms, volcanoes, sea ice, floods) from NASA EONET every 30 minutes, preserving the full geometry timeline so hurricane and iceberg tracks can be replayed on the map
- **World Map Influence**: See which news affect which countries, overlaid with a conflict event heatmap, a natural disasters layer with magnitude-driven marker sizing and movement trails, and toggleable map layers
<img width="1518" height="961" alt="image" src="https://github.com/user-attachments/assets/b888b1da-a736-460f-a7aa-179cb2d66475" />

- **Processing Pipeline**: Fetching of articles, finding entities and categorizing them based on different goals
<img width="1501" height="823" alt="image" src="https://github.com/user-attachments/assets/d422428a-1622-41ad-9962-af3a383c922a" />

- **On-Demand Model Training**: Not implemented yet
- **Search & Analysis**: Basic graph database & viewer show current events, persons and their relations (The default relations are a bit wonky)
<img width="1502" height="831" alt="image" src="https://github.com/user-attachments/assets/beb108e4-f1d9-4e96-89a4-0fa840385b69" />


## Frontend Usability

The frontend is a React SPA at `http://localhost:5173`. The sidebar has seven main sections:

| Menu Item | What it shows |
|---|---|
| **INTERCEPT_FEED** | World map with article, conflict event, and natural disaster markers, clustered by location. A heatmap layer visualizes conflict density (amber → red gradient). Natural disasters render as green markers whose size scales with magnitude (wildfire area, hurricane wind speed, sea-ice extent); hovering or selecting a moving disaster draws a fading directional trail from its earliest observation to its current position. Layer toggles (Articles / Conflicts / Heatmap / Events / Disasters) let you show or hide each data source. Clicking a marker opens the corresponding detail card in the right-hand feed panel — disasters get a dedicated card with magnitude tier, active/closed status, and source links. A floating status widget shows live pipeline health. |
| **INFRASTRUCTURE** | Interactive pipeline topology (React Flow diagram auto-generated from Docker Compose labels), container health, queue metrics, uptime stats, and a live terminal log. |
| **LABELLING** | Two tabs: **LABEL_ASSIGNMENT** — table of articles with filters and manual label editing. **LABEL_SCHEMA** — create, edit, and delete the classification labels that the topic-tagger uses. |
| **ATTRIBUTION** | Two tabs: **ROLE_ASSIGNMENT** — article list with entity role assignments and inline editing. **ROLE_SCHEMA** — manage the entity role types (name, description, color) used by the role-classifier. |
| **AFFILIATION_GRAPH** | Two tabs: **RELATION_GRAPH** — force-directed graph of entities and their relations from Neo4j, with temporal decay controls (lambda slider, min-strength filter). **RELATION_TYPES** — manage relation type definitions (name, description, color, directed/undirected). |
| **SIGNAL_ARCHIVE** | Searchable, paginated card grid of all ingested articles. Click through to the detail page showing full text, extracted entities (with Wikidata IDs and coordinates), and metadata. |
| **TERMINAL_LOG** | Real-time log stream from all services via WebSocket, with per-service filtering, search, and an error panel with acknowledge buttons. |

## Architecture

```mermaid
flowchart LR
    FETCH["article-fetcher"] -- articles.rss --> SCRAPE["article-scraper"]

    SCRAPE --> FO1{{"articles.scraped (fanout)"}}
    FO1 -- articles.raw --> NER["ner-tagger"]
    FO1 -- articles.training --> STORE["article-store"]

    NER -- articles.tagged --> RESOLVE["entity-resolver"]
    RESOLVE -- articles.resolved --> ROLE["role-classifier"]
    ROLE -- articles.role-classified --> TOPIC["topic-tagger"]

    TOPIC --> FO2{{"articles.classified (fanout)"}}
    FO2 -- articles.classified.store --> LABEL["label-updater"]
    FO2 -- articles.classified.relation --> RELEXT["relation-extractor"]

    OSINT["osint-geo-fetcher"] -- conflict_events.raw --> CSTORE["conflict-store"]
    UCDP["ucdp-fetcher"] -- conflict_events.raw --> CSTORE
    GDELT["gdelt-fetcher"] -- conflict_events.raw --> CSTORE

    EONET["nasa-eonet-fetcher"] -- natural_disasters.raw --> DSTORE["disaster-store"]

    FETCH -.- RED[("Redis")]
    OSINT -.- RED
    UCDP -.- RED
    GDELT -.- RED
    EONET -.- RED
    RESOLVE -.- RED
    STORE -.- PG[("PostgreSQL")]
    LABEL -.- PG
    ROLE -.- PG
    TOPIC -.- PG
    RELEXT -.- PG
    CSTORE -.- PG
    DSTORE -.- PG
    RELEXT -.- NEO[("Neo4j")]

    PG -.- API["monitoring-api"]
    NEO -.- API
    API -.- FE["Frontend"]
```

All services communicate via RabbitMQ queues. Queue names are shown on each edge. Fanout exchanges split the stream to multiple consumers. Dashed lines (-.-) show store connections (PostgreSQL for articles + conflict events, Redis for dedup + scheduling, Neo4j for the knowledge graph).

The **conflict data pipeline** runs in parallel to the article pipeline. Three independent fetcher services publish geolocated conflict events to a shared `conflict_events.raw` queue:
- `osint-geo-fetcher` — Bellingcat, Texty, GeoConfirmed, DefMon, CenInfoRes via [osint-geo-extractor](https://github.com/conflict-investigations/osint-geo-extractor) (every 3h)
- `ucdp-fetcher` — [UCDP Candidate Events API](https://ucdp.uu.se/) (weekly)
- `gdelt-fetcher` — [GDELT 2.0](https://www.gdeltproject.org/) material conflict events filtered by CAMEO codes 18/19/20 (every 15 min)

The `conflict-store` consumer writes events to PostgreSQL with dedup on `(source, source_id)`. The frontend renders these as red markers and an aggregated heatmap layer on the world map.

The **natural disasters pipeline** is the third parallel ingest track. A single fetcher service polls NASA's Earth Observatory Natural Event Tracker (EONET) and publishes to its own queue:
- `nasa-eonet-fetcher` — [NASA EONET v3](https://eonet.gsfc.nasa.gov/) events endpoint covering wildfires, severe storms, volcanoes, sea and lake ice, and floods (every 30 min)

The `disaster-store` consumer writes events to the `natural_disasters` table with the full EONET geometry timeline preserved as a JSONB column, so moving events (hurricanes, drifting icebergs) can be rendered with directional track overlays on the map. See [`doc/natural-disasters.md`](doc/natural-disasters.md) for the full design rationale.

### Running Locally

**Important**: Running everything locally will require some resources. Even then, it will be a bit slow; the local NLP categorization isn't optimized and uses CPU only

```bash
# Start the full stack
docker compose -f docker/local/docker-compose.yml up --build -d

# Include all RSS feeds (default runs BBC, Swissinfo + UN News)
docker compose -f docker/local/docker-compose.yml --profile all-feeds up --build -d

# Frontend
open http://localhost:5173

# RabbitMQ management
open http://localhost:15672    # guest / guest

# Neo4j browser
open http://localhost:7474     # neo4j / alexandria

# PostgreSQL
psql postgresql://alexandria:alexandria@localhost:5432/alexandria
```


## Tooling

### Languages & Runtimes

| | |
|---|---|
| **Backend** | Python 3.13+ |
| **Frontend** | TypeScript 5.9 / React 19 |
| **Containers** | Docker & Docker Compose |

### Backend

| Tool | Role |
|---|---|
| [uv](https://docs.astral.sh/uv/) | Package management & dependency locking |
| [FastAPI](https://fastapi.tiangolo.com/) | REST API (monitoring-api) |
| [pika](https://pika.readthedocs.io/) | RabbitMQ client (all services) |
| [psycopg 3](https://www.psycopg.org/psycopg3/) | PostgreSQL driver |
| [httpx](https://www.python-httpx.org/) | Async HTTP client |
| [Ruff](https://docs.astral.sh/ruff/) | Linting & formatting |
| [pytest](https://docs.pytest.org/) | Testing |
| [osint-geo-extractor](https://github.com/conflict-investigations/osint-geo-extractor) | OSINT conflict event data (Bellingcat, Texty, GeoConfirmed, DefMon, CenInfoRes) |

### NLP / ML

| Tool | Role |
|---|---|
| [spaCy](https://spacy.io/) | Named-entity recognition (ner-tagger) |
| [Hugging Face Transformers](https://huggingface.co/docs/transformers/) | Zero-shot classification (role-classifier, topic-tagger, relation-extractor) |
| [PyTorch](https://pytorch.org/) | Inference runtime (CPU-only) |
| [trafilatura](https://trafilatura.readthedocs.io/) | Article text extraction (article-scraper) |
| [feedparser](https://feedparser.readthedocs.io/) | RSS/Atom parsing (article-fetcher) |

### Frontend

| Tool | Role |
|---|---|
| [Vite](https://vite.dev/) | Build tool & dev server |
| [React](https://react.dev/) | UI framework |
| [Tailwind CSS](https://tailwindcss.com/) | Styling |
| [Leaflet](https://leafletjs.com/) / react-leaflet | World map |
| [leaflet.heat](https://github.com/Leaflet/Leaflet.heat) | Conflict event heatmap layer |
| [React Flow](https://reactflow.dev/) | Pipeline topology diagrams |
| [react-force-graph-2d](https://github.com/vasturiano/react-force-graph) | Entity relation graphs |
| [ESLint](https://eslint.org/) | Linting |

### Infrastructure

| Tool | Role |
|---|---|
| [RabbitMQ](https://www.rabbitmq.com/) | Message broker (inter-service queues & fanout exchanges) |
| [PostgreSQL 17](https://www.postgresql.org/) | Primary datastore (articles, conflict events, labels, roles, relations) |
| [Neo4j](https://neo4j.com/) | Graph database (entity relations) |
| [Redis](https://redis.io/) | Cache & scheduling (entity-resolver lookups, feed dedup, fetcher scheduling) |

## Design/UX

Design as well as UX is managed using googles [stitch](https://stitch.withgoogle.com) AI UX tool.
