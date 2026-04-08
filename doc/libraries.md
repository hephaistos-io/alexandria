# Library Reference

A guide to the key libraries used in Alexandria — what each one does, why it was chosen, and what the alternatives look like. Written for someone building their first Python project who wants to understand the ecosystem, not just copy-paste imports.

---

## NLP & Machine Learning

### spaCy (`spacy>=3.8`)

**What it is.** spaCy is an industrial-strength NLP library. It gives you a processing pipeline that takes raw text and returns a structured document object: tokens, part-of-speech tags, dependency parse trees, and named entities. The named-entity recognition (NER) component is what Alexandria uses — it identifies spans of text like "United Nations", "Russia", or "the Kremlin" and labels them as organizations, geopolitical entities, locations, and so on. You load a model once (`spacy.load("en_core_web_sm")`), then call it on any string to get a `Doc` object whose `.ents` attribute is a list of entity spans with `.text`, `.label_`, `.start_char`, and `.end_char`.

**Why it was chosen.** Speed and simplicity. The `en_core_web_sm` model is roughly 12MB and runs a full NER pass on a news article in a few milliseconds on CPU. It loads once into a worker process and handles thousands of articles without restarting. The API is minimal — you call the model like a function and iterate over `.ents`. That is all the ner-tagger service needs. The model uses a convolutional neural network internally; it is not a transformer, which is why it is fast but not state-of-the-art accurate. For a background pipeline that cares about throughput over perfection, that trade-off is right.

The model name `en_core_web_sm` tells you three things: `en` = English, `core` = includes NER + POS + parser, `web` = trained on web text (news, blogs, comments), `sm` = small. spaCy also ships `en_core_web_md`, `en_core_web_lg` (larger word vectors, better accuracy), and `en_core_web_trf` (transformer-based, highest accuracy but ~500MB and much slower). If accuracy on entity detection becomes a bottleneck, upgrading to `en_core_web_trf` is a one-line change in `tagger.py`.

**Alternatives.** NLTK (Natural Language Toolkit) is the older, more academic library. It has NER but it is slower, less accurate, and significantly more effort to use — you chain tokenizers, taggers, and chunkers manually. It is good for learning how NLP pipelines work step by step, but not a practical production choice. Stanza (from Stanford NLP) is a serious alternative: transformer-based by default, very accurate, and supports many languages. The cost is that it is slower and heavier than spaCy's small models. For a pipeline that runs on CPU in Docker containers, Stanza's performance profile is harder to justify. Hugging Face Transformers (see below) can also do NER directly with token classification models, but that adds complexity that spaCy's turnkey models avoid.

---

### Hugging Face Transformers (`transformers>=4.40`)

**What it is.** The `transformers` library from Hugging Face is the standard Python interface to pre-trained neural language models. It provides a `pipeline()` function that hides most of the complexity — you specify a task (e.g. `"zero-shot-classification"`) and a model name, and you get back a callable that accepts text and returns structured results. Under the hood it handles tokenization (splitting text into subword tokens the model understands), running the model forward pass through PyTorch, and post-processing the output logits into human-readable scores. The library also provides lower-level APIs if you need direct access to model internals, but `pipeline()` is the right abstraction for a production service.

**Why it was chosen.** It is the de facto standard for using pre-trained language models in Python. The Model Hub at huggingface.co hosts tens of thousands of models — you reference one by name and the library downloads and caches it automatically on first use. No manual weight files to manage. The `pipeline()` API is deliberately high-level: the role-classifier and relation-extractor both load a zero-shot classification pipeline in two lines and never touch a tokenizer or tensor directly. That is the right level of abstraction for a project where the goal is to *use* NLP, not to implement it. The library is also actively maintained, with the Model Hub growing constantly — swapping to a better model is a one-line change to the `MODEL_NAME` constant.

**Alternatives.** There is no real alternative at this level of the stack. spaCy's transformer models use Hugging Face internally. PyTorch and TensorFlow have their own model-loading utilities, but they require much more manual work. OpenAI / Anthropic APIs give you hosted models without a local inference stack, which is simpler but costs money per call and requires sending article text to an external service — a problem for an OSINT platform that may handle sensitive source material. For this project's use case (free, offline, CPU-capable inference), local models via `transformers` is the only sensible option.

---

### DeBERTa — `MoritzLaurer/deberta-v3-base-zeroshot-v2.0`

**What it is.** DeBERTa (Decoding-enhanced BERT with Disentangled Attention) is a transformer architecture from Microsoft Research. The key improvement over BERT is how it handles the relationship between a word's content and its position: BERT encodes both together, while DeBERTa keeps them separate ("disentangled") and lets the attention mechanism reason about them independently. This makes DeBERTa significantly better at understanding positional context, which matters for tasks that require precise semantic reasoning — like natural language inference (NLI).

The specific variant used here, `MoritzLaurer/deberta-v3-base-zeroshot-v2.0`, is a DeBERTa v3 base model fine-tuned specifically for zero-shot classification. "Zero-shot" means it can classify text into categories it was never explicitly trained on, by framing the problem as NLI: given a premise (article text) and a hypothesis ("In this context, Russia is a target of the conflict described"), does the premise entail, contradict, or is neutral toward the hypothesis? The entailment score becomes the classification confidence. The model weighs roughly 300MB and runs in about 0.5–1 second per inference call on CPU.

**Why it was chosen.** Zero-shot classification is essential for Alexandria because the label schemas (entity roles, relation types) are user-defined at runtime. You cannot train a supervised classifier on labels that may change. The alternative — `facebook/bart-large-mnli` — is the older standard for zero-shot NLI but weighs ~1.6GB and is slower on CPU. This DeBERTa v3 model outperforms it on most zero-shot benchmarks while being roughly one-fifth the size. That makes it viable in a CPU-only container environment. The `v2.0` designation means it was fine-tuned on a wider variety of NLI datasets than v1, improving generalization across domain-specific label descriptions.

**Alternatives.** `facebook/bart-large-mnli` is the most common alternative and works well, but its size makes it impractical for CPU-only deployment. `cross-encoder/nli-deberta-v3-small` is even smaller (~90MB) and faster, at some accuracy cost — if inference speed becomes a bottleneck, that is the first thing to try. GPT-class models via the OpenAI API can do zero-shot classification with a prompt, with better results, but at monetary cost and with network dependency. For a production pipeline handling high article volume, the local DeBERTa model is the right balance of cost, speed, and accuracy.

---

### PyTorch (`torch>=2.2`)

**What it is.** PyTorch is a deep learning framework — a library for defining, training, and running neural network computations. It provides multi-dimensional array operations (via `torch.Tensor`), automatic differentiation for training, and a runtime for executing models efficiently on CPU or GPU. Alexandria does not train any models with PyTorch directly; it is a dependency of `transformers`, which uses PyTorch as its computation backend. When you call `pipeline()`, it is ultimately invoking PyTorch tensor operations to run the model's forward pass.

**Why it was chosen (and the CPU-only wheel trick).** PyTorch is the backend that `transformers` defaults to, so it comes along as an indirect dependency. The critical configuration is in `role-classifier/pyproject.toml` and `relation-extractor/pyproject.toml`:

```toml
[tool.uv.sources]
torch = { index = "pytorch-cpu" }

[[tool.uv.index]]
name = "pytorch-cpu"
url = "https://download.pytorch.org/whl/cpu"
explicit = true
```

By default, `uv` (and `pip`) would install the CUDA-enabled PyTorch wheel, which bundles the NVIDIA CUDA runtime libraries — this makes the wheel approximately 2GB. Since Alexandria runs on CPU in Docker containers with no GPU, that CUDA support is pure waste. The CPU-only wheel from PyTorch's own index is roughly 200MB. This `uv.sources` configuration redirects the `torch` package to that index, making container builds dramatically faster and images much smaller. This is not a hack — it is the officially supported way to install CPU-only PyTorch.

**Alternatives.** TensorFlow is the other major deep learning framework, backed by Google. `transformers` supports both backends, but PyTorch is the more popular choice in the research community, so most models on Hugging Face are published with PyTorch weights first. ONNX Runtime is a lighter-weight alternative for inference only (no training support) that can run transformer models faster than native PyTorch on CPU — worth investigating if inference latency becomes a problem.

---

## Data Ingestion

### feedparser (`feedparser>=6.0`)

**What it is.** feedparser is a Python library for parsing RSS and Atom feeds. You give it a URL (or raw XML string), it returns a structured Python object with a list of entries, each having `.title`, `.link`, `.published`, `.summary`, and so on. It handles the significant variation across feed formats — RSS 0.9, RSS 1.0, RSS 2.0, Atom 0.3, Atom 1.0 — without you needing to care which one you are dealing with. It also handles HTTP redirects, ETags for conditional fetching, and malformed XML that would break a standard XML parser.

**Why it was chosen.** RSS parsing is a solved problem, and feedparser has been the standard Python solution since 2004. The API is a single function call: `feedparser.parse(url)`. It is lightweight with no mandatory dependencies, which keeps the article-fetcher container small. The article-fetcher service needs exactly two things: HTTP access to a feed URL and a structured list of article links with metadata. feedparser provides both without ceremony.

**Alternatives.** You could parse RSS with Python's built-in `xml.etree.ElementTree`, but feed XML is notoriously inconsistent and ElementTree will raise exceptions on malformed input. `atoma` is a modern, typed alternative that is stricter and does less magic — reasonable if you control the feeds. For feeds published by large news organizations (BBC, UN, Reuters), feedparser's tolerance for quirky XML is an advantage.

---

### trafilatura (`trafilatura>=2.0`)

**What it is.** trafilatura is a library for extracting the main text content from web pages. Given an HTML page, it identifies and returns the article body text, discarding navigation, ads, sidebars, comments, and footers. This is called "boilerplate removal" or "content extraction". trafilatura uses a combination of heuristics: it scores HTML elements by their text density, position, tag type, and structural role, then extracts the highest-scoring contiguous block as the main content. It can also extract metadata (title, author, date) and output structured formats like XML.

**Why it was chosen.** The article-scraper service receives a URL from a feed entry and needs to return the full article text. HTML pages are messy — a BBC news article page has hundreds of DOM elements, but only a few paragraphs constitute the actual article. trafilatura handles this reliably across diverse news sources without per-site configuration. Version 2.0 improved speed and accuracy significantly over earlier versions. It also falls back gracefully — if content extraction fails, it returns `None` rather than raising an exception, which the scraper handles cleanly.

**Alternatives.** `newspaper3k` is a popular alternative with a similar API, but it has been poorly maintained for several years and has known compatibility issues with Python 3.10+. `readability-lxml` (a Python port of Mozilla's Readability algorithm, which powers Firefox Reader View) is another strong option — it is accurate but lower-level, returning HTML rather than plain text, so you need to do your own HTML-to-text conversion. BeautifulSoup is not really a competitor here — it is an HTML parsing and traversal library, not a content extractor. You could *implement* content extraction with BeautifulSoup, but you would be reinventing what trafilatura already does. For a project that just needs reliable article text, trafilatura is the right starting point.

---

### httpx (`httpx>=0.28`)

**What it is.** httpx is an HTTP client library for Python. It supports both synchronous and asynchronous request patterns, HTTP/1.1 and HTTP/2, connection pooling, cookies, and redirects. Its API is intentionally similar to the `requests` library (the older standard), so if you have used `requests`, httpx feels familiar. The key difference is that httpx supports `async`/`await` natively — you can make HTTP calls inside async functions without blocking the event loop.

**Why it was chosen.** The monitoring-api needs to make HTTP calls to the Docker daemon and to external services while serving concurrent WebSocket connections. In an async FastAPI application, you cannot use `requests` for outbound calls because `requests` is synchronous — it blocks the thread while waiting for a response, which freezes the event loop and prevents the server from handling other requests. httpx's async client (`httpx.AsyncClient`) integrates naturally with FastAPI's async handlers. httpx is also used in tests as a test client for FastAPI (via `httpx.AsyncClient(app=app)`), which keeps the test dependency simple.

**Alternatives.** `requests` is the most widely used Python HTTP library and is perfectly fine for synchronous code. For async code, `aiohttp` is the other major option — it is older, battle-tested, and has a larger ecosystem. httpx's advantage over aiohttp is API consistency: the same `httpx.Client` / `httpx.AsyncClient` interface works for both sync and async use, and it mirrors `requests` closely enough to be learnable in minutes. For a project with a mix of sync and async code, that consistency reduces cognitive overhead.

---

## Message Queue

### pika (`pika>=1.3`)

**What it is.** pika is the official Python client library for RabbitMQ, which implements the AMQP 0-9-1 protocol. AMQP (Advanced Message Queuing Protocol) is a wire-level protocol for message brokers. pika lets you declare exchanges and queues, publish messages, and consume messages via callback functions. Every Alexandria service except the frontend uses pika — it is the nervous system connecting the pipeline stages. A producer calls `channel.basic_publish()` with a routing key; a consumer declares a queue bound to an exchange and calls `channel.basic_consume()` with a callback function that fires for each message.

**Why it was chosen.** pika is the reference Python client for RabbitMQ, maintained by the RabbitMQ team. It is low-level and explicit — there is no magic, just AMQP primitives. For a project that is partly a learning exercise, that explicitness is valuable: you can see exactly what is happening at the protocol level (exchange declarations, queue bindings, message acknowledgements). All Alexandria services use pika in blocking mode, meaning each service runs a single-threaded consumer loop that blocks on `channel.start_consuming()`. This is simple and reliable for background worker processes that do one thing.

**Why not async pika or alternatives.** `aio-pika` is a well-regarded async wrapper around pika that integrates with Python's `asyncio` event loop. The monitoring-api uses FastAPI (async), so there is an argument for aio-pika there. However, the pattern chosen is to use a background thread for the pika consumer loop, which keeps it isolated from the FastAPI async context. This is a deliberate simplicity trade-off. `kombu` (used by Celery) is a higher-level messaging library that abstracts over multiple backends (RabbitMQ, Redis, SQS). It is powerful but adds indirection that is not needed here — Alexandria's services have direct, known queue topologies.

---

## Databases

### psycopg (`psycopg[binary]>=3.1`)

**What it is.** psycopg is the PostgreSQL database adapter for Python. It implements the Python DB-API 2.0 interface (`PEP 249`), which means it provides a standard `connect()` / `cursor()` / `execute()` / `fetchall()` pattern that works the same way regardless of the underlying database. Version 3 (psycopg3, installed as the `psycopg` package — the version number is in the name) is a complete rewrite of the older `psycopg2`. It adds async support via `psycopg.AsyncConnection`, which is used in FastAPI handlers where you need non-blocking database queries. The `[binary]` extra installs a pre-compiled C extension for better performance; without it you get a pure-Python fallback that is slower.

**Why it was chosen.** psycopg3 is the current standard. It handles type conversion between Python types and PostgreSQL types automatically — Python `datetime` objects map to `TIMESTAMPTZ`, `dict` objects can be passed as `JSONB`, lists map to arrays. The explicit SQL pattern (writing your own `SELECT` statements) is intentional here: it keeps the database interactions visible and learnable. An ORM like SQLAlchemy would hide the SQL, which is the opposite of what a learning project wants. The async support in psycopg3 is first-class and works cleanly with FastAPI's `async def` route handlers.

**Alternatives.** `psycopg2` is the older version, still widely used and very stable. The main reasons to prefer psycopg3 for new projects are: better async support, cleaner API, and active development (psycopg2 is in maintenance mode). `asyncpg` is a fully async PostgreSQL driver with excellent performance — benchmarks show it is often faster than psycopg3 for high-throughput async workloads. However, asyncpg's API diverges from the standard DB-API interface, so it feels less like standard Python database code. For a project that is also a learning exercise, psycopg3's familiar interface is worth more than asyncpg's performance edge.

---

### neo4j (`neo4j>=5.0`)

**What it is.** The `neo4j` package is the official Python driver for Neo4j, a graph database. Neo4j stores data as nodes and relationships rather than rows and tables. The Python driver communicates with Neo4j over the Bolt protocol (a binary, connection-oriented protocol optimized for graph query workloads) and lets you run Cypher queries — Neo4j's query language — from Python. A Cypher query looks like `MATCH (a:Entity)-[r:RELATION]->(b:Entity) RETURN a, r, b`, which reads as: find all paths from any Entity node to another Entity node via a RELATION edge, and return them.

**Why it was chosen.** The relation-extractor writes entity relationships (e.g., "Russia ALLIED_WITH Belarus", "NATO OPPOSES Russia") into Neo4j, and the frontend's affiliation graph reads them back. This is a natural fit for a graph database — asking "what is the transitive network of relationships around this entity?" is a graph traversal that is clumsy to express in SQL but natural in Cypher. The official driver is the right choice over third-party alternatives because it stays current with Neo4j's evolving Bolt protocol versions and authentication changes.

**Alternatives.** You can model graph data in PostgreSQL using recursive CTEs or adjacency list tables, which works for simple cases. If the relation graph stays small (thousands of nodes, tens of thousands of edges), PostgreSQL with a well-indexed edges table is viable. Neo4j's advantage appears when graph traversals get deep (multi-hop paths) or when you need graph-native algorithms like PageRank, community detection, or shortest path — things PostgreSQL's query planner is not designed for. `py2neo` is an older third-party Neo4j client with a higher-level ORM-like API; it is less actively maintained and lags behind official driver updates.

---

### redis (`redis>=5.0`)

**What it is.** Redis is an in-memory data store that supports a variety of data structures: strings, hashes, sets, sorted sets, lists, and more. The `redis` Python package is the standard client library. In Alexandria, Redis serves two roles: (1) a deduplication store — the article-fetcher checks a Redis set before publishing an article URL to ensure it has not been seen before, and (2) a scheduling mechanism — fetcher services record their last-run timestamps in Redis to implement interval-based scheduling without a separate scheduler process.

**Why it was chosen.** Redis is the standard tool for these exact problems. Checking whether a value exists in a Redis set is an O(1) operation regardless of set size — it is far more efficient than querying PostgreSQL for duplicate detection on high-velocity feeds. The Python client is straightforward: `r.sadd("seen_urls", url)` adds to a set, `r.sismember("seen_urls", url)` checks membership. The library also supports Redis Sentinel and Cluster configurations for production resilience, though Alexandria uses standalone Redis.

**Alternatives.** For deduplication at small scale, a PostgreSQL `INSERT ... ON CONFLICT DO NOTHING` with a unique index works cleanly and avoids an extra infrastructure dependency. For scheduling, `APScheduler` is a pure-Python library that runs cron-style jobs within a process. The reason Redis is justified here is that the dedup set grows continuously with article volume, and an in-memory check against Redis stays fast regardless of set size. If you were simplifying the architecture, PostgreSQL-based dedup is a reasonable trade-off.

---

## Web Framework

### FastAPI (`fastapi>=0.115`)

**What it is.** FastAPI is a Python web framework for building HTTP APIs. You define route handlers as Python functions decorated with `@app.get("/path")`, `@app.post("/path")`, etc. What makes FastAPI distinct is its integration with Python type hints: you annotate your function parameters with types, FastAPI automatically validates incoming request data against those types, and it generates interactive OpenAPI documentation (accessible at `/docs`) from the same annotations. Request and response bodies are defined using Pydantic models — Python classes that declare their fields with types and optionally validators.

**Why it was chosen.** The monitoring-api needs to expose PostgreSQL, Neo4j, RabbitMQ, and Docker status to the frontend over HTTP and WebSocket. FastAPI is well-suited to this: it handles HTTP routing, query parameter parsing, JSON serialization, and WebSocket connections in one framework. Its async-first design means route handlers can use `await` to call async database queries without blocking. The automatic OpenAPI documentation at `/docs` is genuinely useful during development — you can test endpoints in the browser without writing a separate test client. FastAPI is also one of the fastest Python web frameworks in benchmarks, because it is built on Starlette (an ASGI framework) and leverages async I/O throughout.

**Alternatives.** Flask is the older, simpler Python web framework. It is synchronous by default and does not have built-in Pydantic integration or automatic API docs. For a simple REST API, Flask is fine. For an async API with structured request/response types and interactive docs, FastAPI saves significant boilerplate. Django REST Framework is the full-stack option — it includes an ORM, admin UI, authentication, and pagination. That breadth is valuable for large applications but is overkill for a single-service monitoring API. Litestar (formerly Starlite) is a newer alternative to FastAPI with similar design goals; it is worth watching but has a smaller ecosystem.

---

### uvicorn (`uvicorn>=0.34`)

**What it is.** uvicorn is an ASGI web server. ASGI (Asynchronous Server Gateway Interface) is the Python standard for connecting async web frameworks to HTTP servers — it is the async successor to WSGI, which is the standard for synchronous frameworks like Flask and Django. When you run `uvicorn monitoring_api.main:app`, uvicorn starts an event loop, binds to a TCP port, accepts HTTP connections, and calls your FastAPI application's ASGI handler for each request. It handles the low-level network I/O so FastAPI can focus on routing and business logic.

**Why it was chosen.** uvicorn is the standard development ASGI server and is recommended in FastAPI's own documentation. It supports HTTP/1.1 and WebSocket, has reasonable defaults, and integrates directly with FastAPI's lifecycle events. For a development or lightly-loaded internal API, uvicorn running in single-process mode is sufficient. It also supports hot-reload during development (`--reload` flag), which restarts the server on file changes.

**Alternatives.** Gunicorn with a uvicorn worker class (`gunicorn -k uvicorn.workers.UvicornWorker`) is the standard production deployment pattern — Gunicorn manages multiple worker processes for parallelism, each running uvicorn. Hypercorn is another ASGI server that supports HTTP/2 and HTTP/3. For Alexandria's internal monitoring API behind Docker Compose networking, single-process uvicorn is appropriate.

---

## Frontend

The frontend is a TypeScript React application. This section is intentionally briefer — the frontend ecosystem is large and each library is more narrowly focused.

### React 19 (`react@19.2.4`) and Vite (`vite@8.0.1`)

React is the UI component framework. You write components as TypeScript functions that return JSX (HTML-like syntax that compiles to JavaScript). React manages re-rendering efficiently when state changes. Version 19 introduced the React Compiler (experimental) and improved concurrent rendering features.

Vite is the build tool and development server. It uses native ES modules in the browser during development (no bundling step, so the dev server starts instantly) and Rollup for production builds. It replaced older tools like Create React App, which used Webpack and was significantly slower. `@vitejs/plugin-react` adds React-specific transforms (JSX compilation, fast refresh during development).

**Alternatives.** Next.js adds server-side rendering, file-based routing, and API routes on top of React — it is the choice when you need SEO, initial page load performance, or a unified full-stack framework. For a dashboard-style internal tool where SEO is irrelevant, the simpler Vite + React SPA setup is appropriate. SvelteKit and Vue are different frameworks with different tradeoffs; React is chosen here for its ecosystem size and learning transferability.

---

### Tailwind CSS (`tailwindcss@4.2.2`)

Tailwind is a utility-first CSS framework. Instead of writing CSS classes like `.article-card { padding: 1rem; background: white; }`, you apply Tailwind's utility classes directly in JSX: `className="p-4 bg-white"`. Tailwind v4 (used here) rewrites the configuration system — you no longer need a `tailwind.config.js` file; the `@tailwindcss/vite` plugin integrates directly into the Vite build and scans your source files for used utility classes.

**Alternatives.** CSS Modules give you component-scoped CSS with no class name collisions, but require writing traditional CSS. styled-components and Emotion allow CSS-in-JS (writing CSS inside TypeScript files). The utility-first approach of Tailwind has won significant adoption in the last few years because it keeps styling co-located with markup without the runtime overhead of CSS-in-JS.

---

### Leaflet (`leaflet@1.9.4`) and react-leaflet (`react-leaflet@5.0.0`)

Leaflet is the dominant open-source JavaScript library for interactive web maps. It renders tiled map backgrounds (from OpenStreetMap or similar providers), handles zooming and panning, and supports markers, polygons, popups, and custom layers. `react-leaflet` wraps Leaflet in React components so you can declare maps declaratively in JSX. `leaflet.heat` adds a heatmap layer using a Gaussian kernel density algorithm — this is what renders the conflict event density visualization on the world map. `react-leaflet-cluster` adds marker clustering, which groups nearby markers into numbered cluster icons to prevent the map from becoming unreadable at low zoom levels.

**Alternatives.** MapLibre GL (the open-source fork of Mapbox GL) renders maps using WebGL and supports vector tiles, which look better at all zoom levels and support rotation and 3D extrusion. It is more powerful but also more complex. For a 2D world map showing markers and a heatmap, Leaflet is simpler and has a larger ecosystem of plugins.

---

### react-force-graph-2d (`react-force-graph-2d@1.29.1`)

This library renders force-directed graphs on an HTML Canvas element. A force-directed graph simulates physics: nodes repel each other, edges act as springs pulling connected nodes together, and the simulation runs until the graph reaches equilibrium. It is used in the affiliation graph view to render the entity relationship network from Neo4j. The `@dagrejs/dagre` package provides a separate hierarchical layout algorithm used by `@xyflow/react` for the pipeline topology diagram (where a force-directed layout would not be appropriate — you want nodes arranged in a left-to-right flow).

**Alternatives.** D3.js provides all the primitives for building force-directed graphs but requires significantly more code. Sigma.js is a WebGL-based graph renderer that handles very large graphs (millions of nodes) more efficiently than Canvas — relevant if the entity graph grows large. Cytoscape.js is another mature graph visualization library with more built-in layout algorithms.

---

### @xyflow/react (`@xyflow/react@12.10.1`)

React Flow (published as `@xyflow/react`) is a library for building node-based editors and diagrams. In Alexandria it renders the pipeline topology view — the diagram showing how services connect through RabbitMQ queues. Nodes and edges are declared as data, and React Flow handles rendering, pan/zoom, and interactive selection. The auto-layout is computed by dagre, which implements the Sugiyama layered graph drawing algorithm (the standard algorithm for producing clean left-to-right DAG layouts).

**Alternatives.** Mermaid.js renders diagrams from a text syntax (the architecture diagram in `README.md` is a Mermaid flowchart). It is simpler but static — you cannot interact with or inspect nodes. For an interactive topology viewer where clicking a node could show service details, React Flow's component model is more appropriate.

---

## Developer Tools

### uv (`uv_build>=0.10.11`)

**What it is.** uv is a Python package manager and build backend written in Rust, developed by Astral (the same team that builds Ruff). It replaces `pip`, `pip-tools`, `virtualenv`, and partially `poetry` with a single fast tool. `uv add <package>` installs a dependency and updates both `pyproject.toml` and `uv.lock`. `uv sync` installs all dependencies from the lockfile. `uv run <command>` runs a command in the project's virtual environment. Because it is written in Rust and uses a parallel dependency resolver, it is typically 10–100x faster than pip for large dependency trees.

**Why it was chosen.** Speed matters during Docker builds — every `uv sync` in a Dockerfile layer takes seconds instead of minutes compared to pip. uv's lockfile format (`uv.lock`) captures exact versions of all transitive dependencies, making builds reproducible. The `[tool.uv.sources]` and `[[tool.uv.index]]` configuration (used to redirect PyTorch to the CPU-only index) is a uv-specific feature that has no clean equivalent in pip. uv is also the build backend for the services themselves (via `uv_build`), which means the same tool handles both dependency management and package building.

**Alternatives.** pip with pip-tools is the classic combination: `pip` installs, `pip-compile` generates locked requirements files. It works but is slower and requires more manual coordination. Poetry is a popular all-in-one tool with dependency management, lockfiles, and packaging. It is slower than uv and has had historical issues with dependency resolution edge cases. Hatch is a newer build tool from the PyPA. For new Python projects in 2025, uv is the choice with the clearest performance and ergonomics advantages.

---

### Ruff (`ruff>=0.11`)

**What it is.** Ruff is a Python linter and code formatter, also written in Rust and developed by Astral. It implements the rules of Flake8, isort, pyupgrade, and more — over 800 lint rules — plus a formatter that produces output equivalent to Black. Because it is compiled to native code and processes files in parallel, it is typically 10–100x faster than running Black + Flake8 + isort separately. A single `ruff check .` replaces `flake8 . && isort --check .`, and `ruff format .` replaces `black .`.

Alexandria's Ruff configuration (in each service's `pyproject.toml`) enables rule sets E (pycodestyle errors), F (Pyflakes), I (isort), and W (pycodestyle warnings). This catches common mistakes: undefined names, unused imports, import ordering violations, and style issues. The `line-length = 100` setting applies to both the linter and formatter.

**Why it was chosen.** One tool instead of three, significantly faster, and identical output to the established tools it replaces. The Python ecosystem spent years with Black for formatting and Flake8 for linting as separate tools that occasionally conflicted (Black's formatting choices sometimes triggered Flake8 warnings that required `# noqa` suppression). Ruff resolves this by owning both concerns. It is also the tool recommended by `uv`'s own documentation for new projects.

**Alternatives.** Black + Flake8 + isort is the traditional stack. It still works and is worth knowing because many existing codebases use it. mypy is a separate type checker that Ruff does not replace — it performs deep type inference across your codebase, which is more powerful than Ruff's type-related lint rules but slower. For a project at Alexandria's scale, running mypy in CI would be a reasonable addition.

---

### pytest (`pytest>=8.0`)

**What it is.** pytest is the standard Python testing framework. You write test functions with names starting with `test_`, use plain `assert` statements for assertions, and run `pytest` to discover and execute all tests. pytest's magic is in its `assert` rewriting: when a test fails, pytest introspects the failed expression and prints a detailed diff showing what the actual and expected values were — much more useful than the bare `AssertionError` you would get from Python's built-in `assert`. Fixtures (the `@pytest.fixture` decorator) provide reusable setup and teardown logic that gets injected into test functions that declare them as parameters.

**Why it was chosen.** pytest is the de facto standard for Python testing. Its convention-over-configuration design (no boilerplate test class, no `self.assertEqual`) makes tests easy to read and write. The fixture system is particularly powerful for setting up database connections, mock objects, or test data once and sharing them across multiple tests. `httpx` is listed as a dev dependency in monitoring-api specifically because pytest uses `httpx.AsyncClient(app=app)` to make test requests to FastAPI without starting a real server — this is the standard testing pattern FastAPI's documentation recommends.

**Alternatives.** `unittest` is Python's built-in testing framework, modeled after JUnit. It is more verbose (you inherit from `TestCase`, use `self.assertEqual`) but requires no installation. For simple scripts, it is fine. For a project of any real size, pytest's ergonomics and ecosystem (plugins like `pytest-asyncio` for async tests, `pytest-cov` for coverage) make it the right choice. `hypothesis` is a property-based testing library that generates test inputs automatically — it complements pytest rather than replacing it.

---

## Sources

Library documentation and version information sourced directly from the service `pyproject.toml` files and `frontend/package.json` in this repository. Architecture context from `README.md`.

Model selection rationale for `MoritzLaurer/deberta-v3-base-zeroshot-v2.0` confirmed from the inline documentation in `services/role-classifier/src/role_classifier/classifier.py` and `services/relation-extractor/src/relation_extractor/extractor.py`.

External references:
- [DeBERTa paper](https://arxiv.org/abs/2006.03654) — He et al., 2020
- [DeBERTa v3](https://arxiv.org/abs/2111.09543) — He et al., 2021
- [MoritzLaurer/deberta-v3-base-zeroshot-v2.0 model card](https://huggingface.co/MoritzLaurer/deberta-v3-base-zeroshot-v2.0)
- [uv documentation](https://docs.astral.sh/uv/)
- [Ruff documentation](https://docs.astral.sh/ruff/)
- [trafilatura documentation](https://trafilatura.readthedocs.io/)
- [psycopg3 documentation](https://www.psycopg.org/psycopg3/docs/)
