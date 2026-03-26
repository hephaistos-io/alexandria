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
- **World Map Influence**: See which news affect which countries
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
| **INTERCEPT_FEED** | World map with article markers clustered by location. Clicking a marker selects the article in the right-hand feed panel (title, summary, labels, source). A floating status widget shows live pipeline health: queue depth, active services, ingest count. |
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

    FETCH -.- RED[("Redis")]
    RESOLVE -.- RED
    STORE -.- PG[("PostgreSQL")]
    LABEL -.- PG
    ROLE -.- PG
    TOPIC -.- PG
    RELEXT -.- PG
    RELEXT -.- NEO[("Neo4j")]

    PG -.- API["monitoring-api"]
    NEO -.- API
    API -.- FE["Frontend"]
```

All services communicate via RabbitMQ queues. Queue names are shown on each edge. Fanout exchanges split the stream to multiple consumers. Dashed lines (-.-)  show store connections (PostgreSQL for label/role/relation type definitions, Redis for caching, Neo4j for the knowledge graph).

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
| [React Flow](https://reactflow.dev/) | Pipeline topology diagrams |
| [react-force-graph-2d](https://github.com/vasturiano/react-force-graph) | Entity relation graphs |
| [ESLint](https://eslint.org/) | Linting |

### Infrastructure

| Tool | Role |
|---|---|
| [RabbitMQ](https://www.rabbitmq.com/) | Message broker (inter-service queues & fanout exchanges) |
| [PostgreSQL 17](https://www.postgresql.org/) | Primary datastore (articles, labels, roles, relations) |
| [Neo4j](https://neo4j.com/) | Graph database (entity relations) |
| [Redis](https://redis.io/) | Cache (entity-resolver lookups, feed dedup) |

## Design/UX

Design as well as UX is managed using googles [stitch](https://stitch.withgoogle.com) AI UX tool.
