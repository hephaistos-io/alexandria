# Glossary

## General Concepts

- **OSINT** — Open Source Intelligence. Gathering and analyzing information from publicly available sources.
- **Data Ingestion** — The process of pulling raw data from external sources into your system.
- **Processing Pipeline** — A sequence of steps that transforms raw data into something structured and usable. In Alexandria, articles flow through: fetcher → scraper → NER tagger → entity resolver → role classifier → topic tagger → label updater / relation extractor.
- **Embeddings** — Numerical vector representations of text (or other data) that capture semantic meaning. Similar texts have similar vectors.
- **Semantic Search** — Searching by meaning rather than exact keyword match, typically using embeddings and vector similarity.
- **ETL** — Extract, Transform, Load. The pattern of pulling data from sources, processing it, and storing the result.
- **Cosine Similarity** — A measure of how similar two vectors are (0 = unrelated, 1 = identical direction). Used to compare embeddings.
- **Escalation Pipeline** — A pattern where cheap/fast methods are tried first, falling back to expensive/slow ones only when needed.
- **MCP** — Model Context Protocol. A standard interface for LLMs to interact with external tools and data sources.
- **Feedback Loop** — A system where outputs (e.g. LLM corrections) feed back as inputs to improve earlier stages (e.g. the alias table).
- **Structured Logging** — Logging with machine-parseable key-value fields (JSON) instead of plain text strings. All Alexandria services use Python's `logging` module with structured output for consistent log parsing.

## Knowledge Representation

- **Knowledge Graph** — A data structure that stores entities (nodes) and typed relationships (edges) between them as triples: `(subject, predicate, object)`. E.g. `(Iran, produces, CrudeOil)`. Enables structured traversal and reasoning.
- **Triple** — The atomic unit of a knowledge graph: `(subject, predicate, object)`. Also called a fact or assertion.
- **Cypher** — Neo4j's declarative query language for graph pattern matching, analogous to SQL for relational databases. Key operations in Alexandria: `MERGE` (create-or-match), `ON CREATE SET` / `ON MATCH SET` (conditional property updates).
- **Entity Linking** — Matching a mention in text (e.g. "The Islamic Republic") to the correct entity in your knowledge graph (Iran). Harder than it sounds.
- **Entity Resolution** — The process of determining whether two entity mentions refer to the same real-world entity, and linking them to a canonical identifier (e.g. Wikidata QID). In Alexandria, the entity-resolver service does this using Wikidata lookups with Redis caching.
- **QID** — A Wikidata identifier for an entity (e.g. Q794 = Iran). Used as the canonical key for entities across the Alexandria pipeline and Neo4j graph.
- **Wikidata** — A free, structured knowledge base maintained by the Wikimedia Foundation. Alexandria uses it for entity resolution — mapping entity names to QIDs and retrieving properties like coordinates (P625) and instance-of types (P31).
- **P625 / P31** — Wikidata property IDs. P625 = "coordinate location" (latitude/longitude), P31 = "instance of" (what type of thing the entity is, e.g. Q6256 = country). Used by entity-resolver to enrich entities with geocoordinates and types.
- **Alias Table** — A Redis-backed lookup table mapping alternative names to canonical entity identifiers. E.g. "The Islamic Republic" → Q794 (Iran). Built up over time as the entity-resolver encounters and resolves new mentions.
- **Ontology** — A formal definition of entity types, relationship types, and rules in a domain. Defines what *kinds* of things exist and how they can relate.
- **SPARQL** — A query language for querying RDF/linked data. Used to query Wikidata.
- **Temporal Decay** — The formula `display_strength = base_strength × exp(−λ × hours_since_last_seen)` used to fade graph edges that haven't been refreshed by recent articles. Lambda (λ) controls the decay rate.
- **Temporal Knowledge Graph** — A knowledge graph where edges carry timestamps and decay functions, so relationships that haven't been re-observed fade out over time.
- **Graph Traversal** — Walking a graph from node to node along edges. "What's within 3 hops of Iran?" is a traversal query.
- **RAG** — Retrieval-Augmented Generation. A pattern where you retrieve relevant documents via search (often vector similarity) and feed them to an LLM as context for generating an answer.
- **Bolt** — Neo4j's binary protocol for client-driver communication (port 7687).
- **CAMEO** — Conflict and Mediation Event Observations. A taxonomy of ~300 event types used by GDELT to classify political events (e.g. code 190 = "Use conventional military force").
- **Goldstein Scale** — A numeric score (-10 to +10) rating the theoretical impact of an event type on country stability. Used in GDELT event records.

## ML / AI Terms

- **NER** — Named Entity Recognition. Identifying things like people, organizations, locations, and dates in text. Alexandria uses spaCy's `en_core_web_trf` transformer model for NER, producing entity labels like GPE, LOC, FAC, ORG, PERSON.
- **GPE / LOC / FAC** — spaCy NER labels for spatial entities. GPE = Geo-Political Entity (countries, cities, states), LOC = non-GPE locations (mountains, rivers), FAC = facilities (airports, bridges). These are the labels that carry geocoordinates in the pipeline.
- **NLI** — Natural Language Inference. A task where a model determines whether a "hypothesis" sentence is entailed by, contradicts, or is neutral to a "premise" sentence. Alexandria repurposes NLI for zero-shot classification: the premise is article text, the hypothesis is a candidate label phrased as a statement, and the entailment score becomes the classification confidence.
- **DeBERTa** — A transformer model architecture by Microsoft. Alexandria uses `MoritzLaurer/deberta-v3-large-zeroshot-v2.0` for zero-shot NLI-based classification in the role-classifier, topic-tagger, and relation-extractor services.
- **Hypothesis Template** — In NLI-based classification, the template string that converts a label into a natural language hypothesis. E.g. for role classification: `"In this context, {entity} is {role_description}"`. The NLI model then scores how well the premise (article text) entails this hypothesis.
- **Zero-Shot Classification** — Using a model to classify text into categories it wasn't explicitly trained on. In Alexandria, implemented via NLI: each candidate label is converted to a hypothesis and scored against the article text. No training data needed — just label descriptions.
- **multi_label** — A parameter in the Hugging Face `zero-shot-classification` pipeline. When `True`, each label is scored independently (an entity can have multiple roles simultaneously). When `False`, scores are normalized to sum to 1 (mutually exclusive labels).
- **Few-Shot** — Training or prompting a model with only a small number of examples.
- **LoRA** — Low-Rank Adaptation. A technique for fine-tuning large models efficiently by only training a small number of added parameters.
- **QLoRA** — Quantized LoRA. Combines model quantization (reducing precision) with LoRA to fine-tune on less GPU memory.
- **PEFT** — Parameter-Efficient Fine-Tuning. A library/approach for fine-tuning models without updating all parameters.
- **Fine-Tuning** — Taking a pre-trained ML model and training it further on your own data to specialize it.
- **Relation Extraction** — The NLP task of identifying typed relationships between entity pairs in text. Alexandria uses zero-shot NLI: for each co-occurring entity pair, it generates hypotheses like `"In this context, {A} {relation_description} {B}"` and scores them.
- **Token Classification** — An ML task where the model assigns a label to each token (word/subword) in the input — NER is a common example.
- **DataFrame** — A tabular data structure (rows and columns), the core abstraction in Polars and pandas.
- **Vector DB** — A database optimized for storing and querying embeddings via similarity search.
- **Pipeline (Hugging Face)** — The `transformers.pipeline()` API provides a high-level interface for common NLP tasks. Alexandria uses `pipeline("zero-shot-classification", model=...)` in the role-classifier, topic-tagger, and relation-extractor.

## Web / API Terms

- **REST API** — Representational State Transfer. A standard pattern for web APIs using HTTP methods (GET, POST, PUT, DELETE).
- **OpenAPI** — A specification for describing REST APIs. FastAPI generates this automatically.
- **Async / asyncio** — Python's built-in framework for concurrent I/O without threads. Lets you handle many network requests without blocking.
- **CORS** — Cross-Origin Resource Sharing. A browser security mechanism that restricts web pages from making requests to a different domain. The monitoring-api enables CORS so the frontend (port 5173) can call the API (port 8000).
- **DI** — Dependency Injection. A pattern where components receive their dependencies from the outside rather than creating them internally.
- **DRF** — Django REST Framework. A toolkit for building REST APIs on top of Django.
- **HTTP/2** — A newer version of the HTTP protocol with multiplexing (multiple requests over one connection) and other performance improvements.
- **RSS/Atom** — XML-based feed formats for publishing frequently updated content (news, blogs). Alexandria's article-fetcher polls RSS feeds on a configurable interval, deduplicating URLs via Redis.
- **Middleware** — Code that sits between the request and your application logic, handling cross-cutting concerns like auth, logging, or throttling.
- **GeoJSON** — An open standard (RFC 7946) for encoding geographic data as JSON. Uses `[longitude, latitude]` coordinate ordering — the opposite of the `[lat, lng]` convention the rest of Alexandria uses. The EONET fetcher's `_extract_point()` and the frontend's `deriveDisasterTrack()` both flip the order explicitly, with comments marking the footgun.

## Infrastructure Terms

- **K8s** — Short for Kubernetes.
- **Kubernetes** — A container orchestration platform. Manages deploying, scaling, and running containers across a cluster of machines.
- **Docker** — A tool for packaging applications into containers — lightweight, portable, isolated environments.
- **Docker Compose** — A tool for defining and running multi-container Docker applications locally using a YAML file. Alexandria's compose file is at `docker/local/docker-compose.yml`.
- **Docker Compose Labels** — Custom metadata on services (e.g. `alexandria.pipeline.inputs`, `alexandria.pipeline.icon`). Alexandria uses these to auto-generate the pipeline topology visualization in the frontend — the monitoring-api reads them via the Docker socket.
- **Docker Compose Profiles** — A way to conditionally include services. Alexandria uses profiles to group optional RSS feed fetchers (e.g. `--profile all-feeds` enables all sources beyond the defaults).
- **Helm** — A package manager for Kubernetes. Helm charts are templated sets of K8s manifests.
- **CronJob** — A Kubernetes resource that runs a container on a schedule (like Unix cron).
- **Argo Workflows** — A Kubernetes-native tool for running complex job pipelines as directed acyclic graphs (DAGs).
- **DAG** — Directed Acyclic Graph. A graph of tasks where each task can depend on others, with no circular dependencies.
- **AMQP** — Advanced Message Queuing Protocol. The wire protocol RabbitMQ speaks on port 5672. Connection strings look like `amqp://user:pass@host:5672`. All Alexandria services connect via AMQP using pika.
- **Fanout Exchange** — A RabbitMQ exchange type that broadcasts every message to all bound queues. Alexandria uses fanout exchanges at two points: `articles.scraped` (fans out to NER tagger + article store) and `articles.classified` (fans out to label updater + relation extractor).
- **Heartbeat (AMQP)** — Periodic keep-alive frames exchanged between a pika client and RabbitMQ. If no heartbeat arrives within the negotiated interval, the connection is considered dead. Long-running message handlers (like NER tagging) must use `connection.process_data_events()` periodically to avoid heartbeat timeouts.
- **StreamLostError** — A pika exception raised when the TCP connection to RabbitMQ drops unexpectedly (network issue, broker restart, missed heartbeats). Alexandria services catch this and reconnect with backoff.
- **Broker** — A message queue that sits between task producers and consumers. RabbitMQ is the broker used in Alexandria.
- **Durable Queue** — A queue declared with `durable=True`. The queue definition (name, settings) survives a RabbitMQ restart. Note: durability does not preserve undelivered messages — that requires persistent messages too.
- **Persistent Message** — A message published with `delivery_mode=Persistent`. RabbitMQ writes it to disk before acknowledging, so it survives a broker restart. Durable queue + persistent messages = no data loss on restart.
- **Prefetch Count** — A RabbitMQ QoS setting (`basic_qos(prefetch_count=N)`) that limits how many unacknowledged messages the broker delivers to one consumer at a time. `prefetch_count=1` means the broker won't send a second message until the first is ACKed. Used in article-scraper to prevent buffering multiple slow HTTP fetches.
- **RabbitMQ** — A message broker designed for reliable message delivery. Supports persistence, acknowledgment (messages aren't lost if a consumer crashes), dead letter queues (parking failed messages), and retry policies. Management UI at port 15672.
- **Redis** — An in-memory key-value store. Used in Alexandria for two purposes: (1) URL deduplication in article-fetcher (prevents re-fetching already-seen articles), and (2) entity alias caching in entity-resolver (maps entity names to Wikidata QIDs).
- **Dead Letter Queue (DLQ)** — A queue where messages go after failing processing too many times. Lets you inspect and replay failures instead of losing them.
- **Message Acknowledgment** — A consumer tells the broker "I've processed this message." If the consumer crashes before acking, the broker redelivers the message to another consumer.
- **KEDA** — Kubernetes Event-Driven Autoscaler. Watches external metrics (like queue depth) and scales deployments, including down to zero replicas.
- **Scale-to-Zero** — A deployment pattern where worker pods are completely removed when there's no work, eliminating idle compute costs. KEDA enables this for Kubernetes.
- **Worker Pool** — A set of long-running processes that pull tasks from a queue and process them. Scales horizontally by adding more workers.
- **Cold Start** — The delay when a container or function needs to start up before it can handle work. Relevant for scale-to-zero patterns.
- **Stateless** — A process that holds no data between requests. Any worker can handle any task, making horizontal scaling simple.

## Data Sources & Services

- **GDELT** — Global Database of Events, Language, and Tone. A free, open platform that monitors world news in 65+ languages, updated every 15 minutes.
- **AP (Associated Press)** — A global wire service providing factual, neutral news coverage. One of the two major wire services (alongside Reuters).
- **Wire Service** — A news agency that supplies stories to multiple outlets (AP, Reuters, AFP). They produce original reporting distributed widely.
- **BigQuery** — Google's serverless data warehouse. Lets you run SQL queries over massive datasets. GDELT's full archive is available there.
- **Rate Limiting** — A server restricting how many requests you can make in a given time period to prevent abuse.
- **EONET** — NASA's Earth Observatory Natural Event Tracker (`eonet.gsfc.nasa.gov/api/v3`). A free, unauthenticated HTTP API that publishes geolocated natural events — wildfires, severe storms, volcanoes, sea and lake ice, floods — aggregated from agencies like GDACS, InciWeb/IRWIN, and the Smithsonian Global Volcanism Program. Alexandria's `nasa-eonet-fetcher` polls the events endpoint every 30 minutes and writes to the `natural_disasters` table. Magnitudes live on individual geometry observations, not the event root — an easy-to-miss API shape that earlier broke magnitude ingest.
- **GDACS** — Global Disaster Alert and Coordination System. A UN/EU joint framework that publishes rapid impact assessments for natural disasters worldwide. Reaches Alexandria as one of EONET's upstream wildfire sources: rows with titles like `"Wildfire in {country} {id}"`, `null` descriptions, and magnitudes in hectare.
- **IRWIN** — Integrated Reporting of Wildland-fire Information. A US Department of the Interior system (`irwin.doi.gov`) that aggregates wildfire incident reports across US federal and state agencies. Reaches Alexandria via EONET as named fire incidents (e.g. "Morrill Wildfire, Garden, Nebraska") with magnitudes in acres and human-readable location descriptions.
- **FIRMS** — NASA Fire Information for Resource Management System. Publishes near-real-time active-fire hotspot detections from the MODIS and VIIRS satellites as point clouds of currently-burning pixels. Not currently wired into Alexandria; `doc/natural-disasters.md` names it as the required upstream for any future feature that wants to render fire behavior (perimeters, spread, hotspot clusters) rather than just event metadata.
- **Saffir-Simpson Scale** — The standard classification of tropical cyclones by sustained wind speed: Tropical Depression (<34 kt), Tropical Storm (34–63 kt), Category 1 (64–82 kt), Cat 2 (83–95), Cat 3 (96–112), Cat 4 (113–136), Cat 5 (137+). Used by `DisasterDetailCard` to turn a raw `magnitudeValue` in knots into a tier badge, and by `AnchorPoint.disasterDotSize()` to scale hurricane markers linearly across the scale.

## Data Storage Terms

- **PostgreSQL** — An open-source relational database. Alexandria uses it to store articles, entities, labels, role types, and relation types.
- **pgvector** — A PostgreSQL extension that adds vector similarity search (for embeddings).
- **JSONB** — A PostgreSQL column type for storing JSON data in a binary format, queryable and indexable.
- **Neo4j** — A graph database with its own query language (Cypher). Alexandria uses Neo4j to store the temporal knowledge graph — entities as nodes, relations as edges with decay metadata.
- **Elasticsearch / OpenSearch** — Search engines for full-text search, analytics, and log aggregation. OpenSearch is an open-source fork of Elasticsearch.
- **Faceted Query** — A search that returns results grouped by categories (facets), like filtering products by brand + price range.

## Python Tooling

- **uv** — A fast Python package manager and resolver, written in Rust. Replaces pip, venv, poetry.
- **Ruff** — A fast Python linter and formatter, written in Rust. Replaces flake8, isort, black.
- **pyproject.toml** — The standard Python project configuration file. Defines dependencies, build settings, and tool config in one place.
- **Lockfile** — A file (e.g., `uv.lock`) that pins exact dependency versions for reproducible installs.
- **venv** — A Python virtual environment. An isolated set of installed packages for a specific project.
- **src layout** — A project structure where your package lives under `src/your_package/` instead of at the repo root, avoiding common import issues.

## Libraries Referenced

### Python

- **FastAPI** — Python web framework for building APIs. Alexandria's monitoring-api uses FastAPI with uvicorn as the ASGI server.
- **uvicorn** — A lightning-fast ASGI server for Python. Runs the monitoring-api's FastAPI application.
- **psycopg** — PostgreSQL adapter for Python (v3). Used by article-store, monitoring-api, and all services that read from Postgres. Replaces the older `psycopg2`.
- **neo4j (driver)** — Official Python driver for Neo4j. Used by relation-extractor (writes) and monitoring-api (reads) to communicate over the Bolt protocol.
- **Litestar** — Alternative Python API framework with built-in dependency injection.
- **Django** — Full-featured Python web framework with ORM, admin, and auth.
- **Celery** — Distributed task queue for Python.
- **ARQ** — Async task queue using Redis.
- **httpx** — Async/sync HTTP client for Python.
- **Scrapy** — Web scraping framework.
- **feedparser** — RSS/Atom feed parser. Used by article-fetcher to parse RSS feeds from news sources.
- **pika** — Python client library for RabbitMQ (AMQP 0-9-1). Used in all Alexandria services that produce or consume queue messages. Provides both blocking and async connection adapters; Alexandria uses `BlockingConnection`.
- **trafilatura** — Extracts main text content from web pages. Handles boilerplate removal (navigation, ads, footers). Used by article-scraper to clean raw HTML into plain text for downstream NLP.
- **playwright** — Browser automation, used for scraping JS-rendered pages.
- **spaCy** — Industrial-strength NLP library. Alexandria uses the `en_core_web_trf` transformer-based model for NER in the ner-tagger service, producing entity spans with labels (GPE, LOC, FAC, ORG, PERSON, etc.).
- **GLiNER** — Zero-shot NER model.
- **Hugging Face transformers** — Library for using and fine-tuning pre-trained ML models. Alexandria uses the `pipeline("zero-shot-classification")` API for NLI-based classification in role-classifier, topic-tagger, and relation-extractor.
- **sentence-transformers** — Library for generating text embeddings.
- **scikit-learn** — Classical machine learning library (no deep learning).
- **Polars** — Fast DataFrame library written in Rust.
- **pandas** — The original Python DataFrame library, widely used but slower than Polars.
- **Prefect** — Workflow orchestration / pipeline tool.
- **Airflow** — Apache's workflow orchestration platform (heavier than Prefect).
- **Pydantic** — Data validation library using Python type hints. Core to FastAPI.
- **gdeltdoc** — Python client for the GDELT DOC 2.0 API. Returns results as DataFrames.
- **gdeltPyR** — Python library for downloading GDELT raw data files.
- **NetworkX** — Python library for creating and analyzing graphs. In-memory, good for prototyping knowledge graphs.
- **rdflib** — Python library for working with RDF (Resource Description Framework) linked data formats.
- **qwikidata** — Python library for accessing Wikidata. Used by entity-resolver for QID lookups and property retrieval.
- **REBEL** — A model that extracts `(subject, relation, object)` triples from text. Research-grade.
- **Qdrant** — Vector database for similarity search.

### Frontend / JavaScript

- **React** — JavaScript UI library for building component-based interfaces. Alexandria's frontend is a React SPA.
- **TypeScript** — Typed superset of JavaScript. The entire Alexandria frontend is written in TypeScript.
- **Vite** — Fast frontend build tool and dev server. Provides HMR (Hot Module Replacement) during development and optimized production builds.
- **Tailwind CSS** — Utility-first CSS framework. Alexandria uses Tailwind v4 with a custom dark theme defined in `index.css` using CSS custom properties (Material Design 3 color tokens).
- **Leaflet / react-leaflet** — Open-source map library. The GlobalOverviewPage uses Leaflet via react-leaflet bindings to render a dark tactical map with article markers, clustering, and arc overlays.
- **react-leaflet-cluster** — Marker clustering plugin for react-leaflet. Groups nearby map markers into count badges at low zoom, with spiderfy for overlapping markers at high zoom.
- **React Flow (@xyflow/react)** — Library for building interactive node-based graphs and diagrams. Used in the pipeline topology visualization page.
- **react-force-graph-2d** — Lightweight force-directed graph renderer. Used in the AffiliationGraphPage to visualize the temporal knowledge graph with zoom/pan and directed edges.
- **Material Symbols** — Google's variable icon font. Used throughout the frontend for UI icons (e.g. `public`, `account_tree`, `rss_feed`).
