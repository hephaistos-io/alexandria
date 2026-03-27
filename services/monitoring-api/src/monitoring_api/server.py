"""FastAPI application — /health and /api/status endpoints.

Key patterns used here:

asynccontextmanager lifespan
----------------------------
FastAPI replaced the older @app.on_event("startup") hooks with a single
'lifespan' context manager. Code before the `yield` runs at startup; code
after runs at shutdown. This is where we initialise and clean up clients.

run_in_executor
---------------
The Docker SDK is synchronous (it uses the requests library internally).
Calling a sync function directly inside an async route handler would block
the entire event loop — no other requests could be served while we wait for
Docker to respond.

`asyncio.get_event_loop().run_in_executor(None, fn)` offloads the sync call
to Python's default thread pool executor. `None` means "use the default
ThreadPoolExecutor". The event loop remains free to handle other requests
while the thread runs.

dataclasses_to_dict
-------------------
Python's `dataclasses.asdict()` recursively converts a dataclass (and any
nested dataclasses) into plain dicts. FastAPI can then serialise that dict
to JSON automatically.
"""

import asyncio
import dataclasses
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pika
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from monitoring_api.article_client import (
    MAX_LABELS,
    ArticleClient,
)
from monitoring_api.conflict_client import ConflictClient
from monitoring_api.db_client import DbClient, DbStats
from monitoring_api.docker_client import ContainerStatus, DockerClient
from monitoring_api.graph_client import GraphClient
from monitoring_api.label_client import ClassificationLabel, ClassificationLabelClient
from monitoring_api.log_streamer import LogStreamer
from monitoring_api.rabbitmq_client import BindingInfo, ExchangeInfo, QueueInfo, RabbitMQClient
from monitoring_api.relation_type_client import RelationType, RelationTypeClient
from monitoring_api.role_type_client import EntityRoleType, EntityRoleTypeClient
from monitoring_api.topology_builder import PipelineTopology, build_topology

logger = logging.getLogger(__name__)


class LabelUpdate(BaseModel):
    """Request body for the PATCH /api/labelling/articles/{id}/labels endpoint.

    Pydantic's BaseModel gives us automatic JSON parsing and type validation.
    FastAPI will return a 422 if the request body doesn't match this schema
    (e.g. missing 'labels' key, or labels is not a list).
    """

    labels: list[str]


class ClassificationLabelCreate(BaseModel):
    """Request body for POST /api/classification/labels."""

    name: str
    description: str
    color: str = "#76A9FA"


class ClassificationLabelUpdate(BaseModel):
    """Request body for PATCH /api/classification/labels/{id}.

    All fields are optional — only provided fields will be updated.
    """

    description: str | None = None
    color: str | None = None
    enabled: bool | None = None


class CreateRoleType(BaseModel):
    """Request body for POST /api/attribution/role-types."""

    name: str
    description: str
    color: str = "#76A9FA"


class UpdateRoleType(BaseModel):
    """Request body for PATCH /api/attribution/role-types/{id}.

    All fields are optional — only provided fields will be updated.
    """

    description: str | None = None
    color: str | None = None
    enabled: bool | None = None


class CreateRelationType(BaseModel):
    """Request body for POST /api/graph/relation-types."""

    name: str
    description: str
    color: str = "#76A9FA"
    directed: bool = True


class UpdateRelationType(BaseModel):
    """Request body for PATCH /api/graph/relation-types/{id}.

    All fields are optional — only provided fields will be updated.
    """

    description: str | None = None
    color: str | None = None
    directed: bool | None = None
    enabled: bool | None = None


class EntityRoleUpdate(BaseModel):
    """Request body for PATCH /api/attribution/articles/{article_id}/roles.

    roles maps Wikidata entity IDs to role names, e.g.:
        {"Q794": "AFFECTED", "Q30": "SOURCE"}

    An empty dict clears the annotation (sets manual_entity_roles to NULL).
    """

    roles: dict


def _read_env() -> dict:
    """Read configuration from environment variables with sensible defaults."""
    return {
        "database_url": os.environ.get("DATABASE_URL", ""),
        "rabbitmq_management_url": os.environ.get(
            "RABBITMQ_MANAGEMENT_URL", "http://rabbitmq:15672"
        ),
        "rabbitmq_user": os.environ.get("RABBITMQ_USER", "guest"),
        "rabbitmq_password": os.environ.get("RABBITMQ_PASSWORD", "guest"),
        "docker_project": os.environ.get("COMPOSE_PROJECT_NAME", "alexandria"),
        "neo4j_url": os.environ.get("NEO4J_URL", ""),
        "neo4j_auth": os.environ.get("NEO4J_AUTH", "neo4j/alexandria"),
    }


def create_app(
    docker_client: DockerClient | None = None,
    rabbitmq_client: RabbitMQClient | None = None,
    db_client: DbClient | None = None,
    article_client: ArticleClient | None = None,
    label_client: ClassificationLabelClient | None = None,
    role_type_client: EntityRoleTypeClient | None = None,
    relation_type_client: RelationTypeClient | None = None,
    graph_client: GraphClient | None = None,
    conflict_client: ConflictClient | None = None,
) -> FastAPI:
    """Factory function that builds and returns the FastAPI application.

    Accepts optional pre-built clients so tests can inject mocks without
    touching environment variables or the filesystem.

    The pattern of accepting dependencies as constructor arguments (rather
    than reading them from global state) is called Dependency Injection.
    It makes the code much easier to test in isolation.
    """
    config = _read_env()

    # We store clients in a mutable container so the lifespan closure can
    # assign into it. A simple dict works fine here.
    state: dict = {
        "docker": docker_client,
        "rabbitmq": rabbitmq_client,
        "db": db_client,
        "articles": article_client,
        "labels": label_client,
        "role_types": role_type_client,
        "relation_types": relation_type_client,
        "graph": graph_client,
        "conflicts": conflict_client,
        "env": config,
    }

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # --- Startup ---
        # Only create clients that weren't injected (i.e. not running tests).
        if state["docker"] is None:
            state["docker"] = DockerClient(project_name=config["docker_project"])
        if state["rabbitmq"] is None:
            state["rabbitmq"] = RabbitMQClient(
                management_url=config["rabbitmq_management_url"],
                user=config["rabbitmq_user"],
                password=config["rabbitmq_password"],
            )
        if state["db"] is None and config["database_url"]:
            state["db"] = DbClient(database_url=config["database_url"])
        if state["articles"] is None and config["database_url"]:
            state["articles"] = ArticleClient(database_url=config["database_url"])
        if state["labels"] is None and config["database_url"]:
            state["labels"] = ClassificationLabelClient(database_url=config["database_url"])
        if state["role_types"] is None and config["database_url"]:
            state["role_types"] = EntityRoleTypeClient(database_url=config["database_url"])
        if state["relation_types"] is None and config["database_url"]:
            state["relation_types"] = RelationTypeClient(database_url=config["database_url"])
        if state["graph"] is None and config["neo4j_url"]:
            user, password = config["neo4j_auth"].split("/", 1)
            state["graph"] = GraphClient(uri=config["neo4j_url"], auth=(user, password))
        if state["conflicts"] is None and config["database_url"]:
            state["conflicts"] = ConflictClient(database_url=config["database_url"])

        logger.info("Monitoring API started")
        yield
        # --- Shutdown ---
        if state["rabbitmq"] is not None:
            await state["rabbitmq"].aclose()
        if state["graph"] is not None:
            state["graph"].close()
        logger.info("Monitoring API stopped")

    app = FastAPI(title="Alexandria Monitoring API", lifespan=lifespan)

    # CORS origins: configurable via CORS_ORIGINS env var (comma-separated).
    # Defaults to ["*"] for local development. In production, set e.g.
    # CORS_ORIGINS=https://dashboard.example.com
    cors_origins_raw = os.environ.get("CORS_ORIGINS", "*")
    cors_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/status")
    async def status() -> dict:
        loop = asyncio.get_event_loop()

        # Docker SDK is sync — run it in a thread so we don't block the loop.
        docker_client_ref: DockerClient | None = state["docker"]
        if docker_client_ref is not None:
            containers: list[ContainerStatus] = await loop.run_in_executor(
                None, docker_client_ref.get_containers
            )
        else:
            containers = []

        # RabbitMQ calls are already async — await them directly.
        rabbitmq_ref: RabbitMQClient | None = state["rabbitmq"]
        if rabbitmq_ref is not None:
            queues: list[QueueInfo]
            exchanges: list[ExchangeInfo]
            queues, exchanges = await asyncio.gather(
                rabbitmq_ref.get_queues(),
                rabbitmq_ref.get_exchanges(),
            )
        else:
            queues = []
            exchanges = []

        # DB client is sync — also run in executor.
        db_ref: DbClient | None = state["db"]
        db_stats: DbStats | None = None
        if db_ref is not None:
            db_stats = await loop.run_in_executor(None, db_ref.get_stats)

        # Build the response dict. We serialise dataclasses manually so we can
        # control datetime formatting (ISO 8601 with 'Z' suffix).
        return {
            "containers": [dataclasses.asdict(c) for c in containers],
            "queues": [dataclasses.asdict(q) for q in queues],
            "exchanges": [dataclasses.asdict(e) for e in exchanges],
            "db": _format_db(db_stats),
        }

    @app.websocket("/ws/logs")
    async def logs_websocket(websocket: WebSocket) -> None:
        """Stream Docker container logs to the browser over WebSocket.

        Each message sent over the socket is a JSON string with this shape:
            {"ts": "...", "level": "info", "service": "article-fetcher",
             "logger": "...", "message": "..."}

        The connection stays open, streaming new log lines as they arrive,
        until the client disconnects or an error occurs.

        WebSocket lifecycle:
          1. accept()  — completes the HTTP upgrade handshake
          2. stream logs until client disconnects (WebSocketDisconnect raised)
          3. The LogStreamer's tasks are cancelled in its finally block
        """
        await websocket.accept()

        docker_ref: DockerClient | None = state["docker"]
        if docker_ref is None:
            # Docker client not initialised — send an error and close.
            await websocket.send_json(
                {
                    "ts": "1970-01-01T00:00:00Z",
                    "level": "error",
                    "service": "monitoring-api",
                    "message": "Docker client not available",
                }
            )
            await websocket.close()
            return

        streamer = LogStreamer(docker_ref)
        try:
            logger.info("Starting log stream for WebSocket client")
            count = 0
            async for entry in streamer.stream():
                # WebSocketDisconnect is raised by send_json if the client
                # has already gone away — we catch it below.
                await websocket.send_json(entry)
                count += 1
                if count == 1:
                    logger.info("First log entry sent to WebSocket client")
            logger.info("Log stream ended after %d entries", count)
        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected from /ws/logs")
        except Exception as exc:
            logger.warning("Unexpected error in /ws/logs: %s", exc, exc_info=True)
        finally:
            # Ensure all background tailing threads are stopped even if
            # the generator was not fully consumed (e.g. client disconnected
            # mid-stream before CancelledError propagated through stream()).
            streamer.stop()

    # ------------------------------------------------------------------
    # Dashboard endpoints
    # ------------------------------------------------------------------

    @app.get("/api/dashboard/articles", response_model=None)
    async def dashboard_articles(limit: int = 20):
        """Return recent articles with entities for the dashboard map and feed."""
        loop = asyncio.get_event_loop()
        articles_ref: ArticleClient | None = state["articles"]
        if articles_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )
        result = await loop.run_in_executor(
            None,
            lambda: articles_ref.get_dashboard_articles(min(limit, 50)),
        )
        if result is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )
        return [dataclasses.asdict(a) for a in result]

    @app.get("/api/dashboard/conflict-events", response_model=None)
    async def dashboard_conflict_events(limit: int = 200):
        """Return recent conflict events for the dashboard map."""
        loop = asyncio.get_event_loop()
        conflict_ref: ConflictClient | None = state["conflicts"]
        if conflict_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )
        try:
            result = await loop.run_in_executor(
                None,
                lambda: conflict_ref.get_dashboard_events(min(limit, 500)),
            )
            return [dataclasses.asdict(e) for e in result]
        except Exception:
            logger.exception("Failed to fetch conflict events")
            return Response(
                content=json.dumps({"error": "internal"}),
                status_code=500,
                media_type="application/json",
            )

    # ------------------------------------------------------------------
    # Archive endpoints
    # ------------------------------------------------------------------

    @app.get("/api/archive/articles", response_model=None)
    async def archive_articles(
        page: int = 1,
        page_size: int = 9,
        search: str = "",
        sort_dir: str = "desc",
    ):
        """Return a paginated list of articles for the Signal Archive.

        Supports optional title search and sort direction. page_size is
        capped at 50 to prevent runaway queries.
        """
        if sort_dir not in {"asc", "desc"}:
            return Response(
                content=json.dumps({"error": f"Invalid sort_dir: {sort_dir}"}),
                status_code=422,
                media_type="application/json",
            )

        loop = asyncio.get_event_loop()
        articles_ref: ArticleClient | None = state["articles"]
        if articles_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        result = await loop.run_in_executor(
            None,
            lambda: articles_ref.get_archive_articles(page, min(page_size, 50), search, sort_dir),
        )
        if result is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )
        return dataclasses.asdict(result)

    @app.get("/api/archive/articles/{article_id}", response_model=None)
    async def archive_article_detail(article_id: int):
        """Return the full detail for a single article."""
        loop = asyncio.get_event_loop()
        articles_ref: ArticleClient | None = state["articles"]
        if articles_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        result = await loop.run_in_executor(
            None,
            lambda: articles_ref.get_article_detail(article_id),
        )
        if result is None:
            return Response(
                content=json.dumps({"error": "Article not found"}),
                status_code=404,
                media_type="application/json",
            )
        return dataclasses.asdict(result)

    @app.post("/api/archive/articles/{article_id}/reparse", response_model=None)
    async def archive_article_reparse(article_id: int):
        """Delete an article and re-queue it for the full ingestion pipeline.

        The article's current data (url, source, title, etc.) is read before
        deletion and published to the articles.rss queue so the fetchers pick
        it up for a fresh scrape-and-parse cycle.

        Steps:
          1. Fetch full article detail (404 if not found).
          2. Delete the article row from the database.
          3. Publish a minimal re-fetch message to the articles.rss queue.
          4. Return {"status": "queued", "url": <url>}.
        """
        articles_ref: ArticleClient | None = state["articles"]
        if articles_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        env = state["env"]

        def _reparse() -> dict | None:
            """Synchronous block: fetch, publish, then delete — all blocking I/O.

            Publishes to RabbitMQ BEFORE deleting from the database. If the
            publish fails, the article remains intact — no data loss.

            Returns a result dict on success, or None if the article was not found.
            Raises on publish failure so the caller can surface the error.
            """
            article = articles_ref.get_article_detail(article_id)
            if article is None:
                return None

            message = {
                "source": article.source,
                "origin": article.origin,
                "title": article.title,
                "url": article.url,
                "summary": article.summary or "",
                "published": article.published_at,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }

            rabbitmq_host = os.environ.get("RABBITMQ_HOST", "rabbitmq")
            amqp_url = (
                f"amqp://{env['rabbitmq_user']}:{env['rabbitmq_password']}"
                f"@{rabbitmq_host}:5672/"
            )

            connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
            try:
                channel = connection.channel()
                channel.queue_declare(queue="articles.rss", durable=True)
                channel.basic_publish(
                    exchange="",
                    routing_key="articles.rss",
                    body=json.dumps(message),
                    properties=pika.BasicProperties(
                        delivery_mode=pika.DeliveryMode.Persistent,
                        content_type="application/json",
                    ),
                )
            finally:
                connection.close()

            # Only delete after successful publish — if we got here, the
            # message is safely in the queue.
            articles_ref.delete_article(article_id)

            return {"status": "queued", "url": article.url}

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, _reparse)
        except Exception as exc:
            logger.warning("Reparse failed for article %s: %s", article_id, exc)
            return Response(
                content=json.dumps({"error": "Failed to queue article for reparse"}),
                status_code=502,
                media_type="application/json",
            )

        if result is None:
            return Response(
                content=json.dumps({"error": "Article not found"}),
                status_code=404,
                media_type="application/json",
            )

        return result

    # TODO: add authentication if this API is ever exposed beyond localhost.
    #       reparse-all is destructive (deletes all articles) and has no auth guard.
    @app.post("/api/archive/articles/reparse-all", response_model=None)
    async def archive_reparse_all():
        """Delete all articles and re-queue them for a full re-scrape.

        This is destructive: every article row is deleted from the DB,
        then each article's source URL is pushed to ``articles.rss`` so
        the scraper pipeline re-fetches and re-processes them from scratch
        (matching the single-article reparse behaviour).

        Articles will gradually re-appear as the scrapers process them.

        Returns {"status": "queued", "count": N}.
        """
        articles_ref: ArticleClient | None = state["articles"]
        if articles_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        env = state["env"]

        def _reparse_all() -> dict:
            payloads = articles_ref.get_reparse_payloads()
            if payloads is None:
                raise RuntimeError("Failed to read articles from database")
            if not payloads:
                return {"status": "queued", "count": 0}

            rabbitmq_host = os.environ.get("RABBITMQ_HOST", "rabbitmq")
            amqp_url = (
                f"amqp://{env['rabbitmq_user']}:{env['rabbitmq_password']}"
                f"@{rabbitmq_host}:5672/"
            )

            # Publish all messages BEFORE deleting from the database.
            # If any publish fails, the articles remain intact — no data loss.
            connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
            try:
                channel = connection.channel()
                channel.queue_declare(queue="articles.rss", durable=True)

                for payload in payloads:
                    channel.basic_publish(
                        exchange="",
                        routing_key="articles.rss",
                        body=json.dumps(payload),
                        properties=pika.BasicProperties(
                            delivery_mode=pika.DeliveryMode.Persistent,
                            content_type="application/json",
                        ),
                    )
            finally:
                connection.close()

            # Only delete after all messages are safely published.
            articles_ref.delete_all_articles()
            return {"status": "queued", "count": len(payloads)}

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, _reparse_all)
        except Exception as exc:
            logger.warning("Reparse-all failed: %s", exc)
            return Response(
                content=json.dumps({"error": "Failed to queue articles for reparse"}),
                status_code=502,
                media_type="application/json",
            )

        return result

    # ------------------------------------------------------------------
    # Labelling endpoints
    # ------------------------------------------------------------------

    @app.get("/api/labelling/stats", response_model=None)
    async def labelling_stats():
        loop = asyncio.get_event_loop()
        articles_ref: ArticleClient | None = state["articles"]
        if articles_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        result = await loop.run_in_executor(None, articles_ref.get_labelling_stats)
        if result is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )
        return dataclasses.asdict(result)

    @app.get("/api/labelling/articles", response_model=None)
    async def labelling_articles(
        page: int = 1,
        page_size: int = 10,
        filter: str = "all",
        sort_by: str = "date_ingested",
        sort_dir: str = "desc",
    ):
        # Validate query parameters against whitelists
        if filter not in {"all", "labelled", "unlabelled", "auto_labelled"}:
            return Response(
                content=json.dumps({"error": f"Invalid filter: {filter}"}),
                status_code=422,
                media_type="application/json",
            )
        if sort_by not in {"date_ingested", "source_origin"}:
            return Response(
                content=json.dumps({"error": f"Invalid sort_by: {sort_by}"}),
                status_code=422,
                media_type="application/json",
            )
        if sort_dir not in {"asc", "desc"}:
            return Response(
                content=json.dumps({"error": f"Invalid sort_dir: {sort_dir}"}),
                status_code=422,
                media_type="application/json",
            )

        loop = asyncio.get_event_loop()
        articles_ref: ArticleClient | None = state["articles"]
        if articles_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        result = await loop.run_in_executor(
            None,
            lambda: articles_ref.get_articles(
                page, min(page_size, 50), filter, sort_by, sort_dir
            ),
        )
        if result is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )
        return dataclasses.asdict(result)

    @app.patch("/api/labelling/articles/{article_id}/labels", response_model=None)
    async def update_article_labels(article_id: int, body: LabelUpdate):
        labels = body.labels

        # Validate label count
        if len(labels) > MAX_LABELS:
            return Response(
                content=json.dumps(
                    {"error": f"Too many labels: maximum is {MAX_LABELS}, got {len(labels)}"}
                ),
                status_code=422,
                media_type="application/json",
            )

        # Validate label names against the classification_labels table.
        # This is dynamic — new labels created via the Schema Manager are
        # immediately accepted without a service restart.
        loop = asyncio.get_event_loop()
        labels_ref: ClassificationLabelClient | None = state["labels"]
        if labels_ref is not None and labels:
            db_labels = await loop.run_in_executor(None, labels_ref.get_labels)
            if db_labels is None:
                return Response(
                    content=json.dumps({"error": "unavailable"}),
                    status_code=503,
                    media_type="application/json",
                )
            allowed = {lbl.name for lbl in db_labels}
            invalid = [label for label in labels if label not in allowed]
            if invalid:
                return Response(
                    content=json.dumps(
                        {
                            "error": f"Invalid label(s): {', '.join(invalid)}. "
                            f"Allowed: {', '.join(sorted(allowed))}"
                        }
                    ),
                    status_code=422,
                    media_type="application/json",
                )

        articles_ref: ArticleClient | None = state["articles"]
        if articles_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        found = await loop.run_in_executor(
            None,
            lambda: articles_ref.update_labels(article_id, labels),
        )
        if not found:
            return Response(
                content=json.dumps({"error": f"Article {article_id} not found"}),
                status_code=404,
                media_type="application/json",
            )

        return {"ok": True, "article_id": article_id, "labels": labels}

    @app.get("/api/topology", response_model=None)
    async def topology() -> dict:
        """Return the pipeline topology: stages and connections.

        Fetches pipeline labels from Docker containers and exchange→queue bindings
        from RabbitMQ, then delegates to build_topology() to produce the graph.

        The response matches the TypeScript PipelineTopology interface:
          { stages: PipelineStage[], connections: StageConnection[] }

        Note on 'from' vs 'from_id': Python forbids 'from' as a field name
        (it's a keyword). Our dataclass uses 'from_id', so we manually rename
        it to 'from' in the JSON output to match the frontend contract.
        """
        loop = asyncio.get_event_loop()

        # Docker is sync — run in executor.
        docker_ref: DockerClient | None = state["docker"]
        if docker_ref is not None:
            pipeline_labels = await loop.run_in_executor(
                None, docker_ref.get_pipeline_labels
            )
        else:
            pipeline_labels = {}

        # RabbitMQ is async.
        rabbitmq_ref: RabbitMQClient | None = state["rabbitmq"]
        if rabbitmq_ref is not None:
            bindings: list[BindingInfo] = await rabbitmq_ref.get_bindings()
        else:
            bindings = []

        topo: PipelineTopology = build_topology(pipeline_labels, bindings)

        # Serialise stages: convert StageMatch and StageVisual sub-dataclasses.
        stages_out = []
        for stage in topo.stages:
            stages_out.append({
                "id": stage.id,
                "column": stage.column,
                "match": {
                    k: v
                    for k, v in dataclasses.asdict(stage.match).items()
                    if v is not None
                },
                "visual": {
                    # Rename 'accent' → 'accentColor' to match the frontend
                    # StageVisual interface (Python can't easily use camelCase
                    # field names, so we rename during serialisation).
                    ("accentColor" if k == "accent" else k): v
                    for k, v in dataclasses.asdict(stage.visual).items()
                    if v is not None
                },
                "scalable": stage.scalable,
            })

        # Serialise connections: rename 'from_id' → 'from' for the frontend.
        connections_out = [
            {"from": conn.from_id, "to": conn.to_id, "dashed": conn.dashed}
            for conn in topo.connections
        ]

        return {"stages": stages_out, "connections": connections_out}

    @app.get("/api/labelling/export", response_model=None)
    async def labelling_export():
        loop = asyncio.get_event_loop()
        articles_ref: ArticleClient | None = state["articles"]
        if articles_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        rows = await loop.run_in_executor(None, articles_ref.get_unlabelled_jsonl)
        if rows is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        # Build NDJSON (newline-delimited JSON): one JSON object per line.
        lines = [json.dumps(row) for row in rows]
        content = "\n".join(lines)
        if lines:
            content += "\n"

        return Response(
            content=content,
            media_type="application/x-ndjson",
            headers={"Content-Disposition": 'attachment; filename="unlabelled_articles.jsonl"'},
        )

    # ------------------------------------------------------------------
    # Classification label endpoints
    # ------------------------------------------------------------------

    @app.get("/api/classification/labels", response_model=None)
    async def list_classification_labels():
        """Return all classification label definitions."""
        loop = asyncio.get_event_loop()
        labels_ref: ClassificationLabelClient | None = state["labels"]
        if labels_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        result = await loop.run_in_executor(None, labels_ref.get_labels)
        if result is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        return [dataclasses.asdict(lbl) for lbl in result]

    @app.post("/api/classification/labels", response_model=None)
    async def create_classification_label(body: ClassificationLabelCreate):
        """Create a new classification label."""
        labels_ref: ClassificationLabelClient | None = state["labels"]
        if labels_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        loop = asyncio.get_event_loop()
        result: ClassificationLabel | None = await loop.run_in_executor(
            None,
            lambda: labels_ref.create_label(body.name, body.description, body.color),
        )

        if result is None:
            # create_label returns None on DB error (e.g. duplicate name)
            return Response(
                content=json.dumps({"error": f"Could not create label '{body.name}'"}),
                status_code=409,
                media_type="application/json",
            )

        return dataclasses.asdict(result)

    @app.patch("/api/classification/labels/{label_id}", response_model=None)
    async def update_classification_label(label_id: int, body: ClassificationLabelUpdate):
        """Update description, color, and/or enabled flag for a label."""
        labels_ref: ClassificationLabelClient | None = state["labels"]
        if labels_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        loop = asyncio.get_event_loop()
        result: ClassificationLabel | None = await loop.run_in_executor(
            None,
            lambda: labels_ref.update_label(
                label_id,
                description=body.description,
                color=body.color,
                enabled=body.enabled,
            ),
        )

        if result is None:
            return Response(
                content=json.dumps({"error": f"Label {label_id} not found"}),
                status_code=404,
                media_type="application/json",
            )

        return dataclasses.asdict(result)

    @app.delete("/api/classification/labels/{label_id}", response_model=None)
    async def delete_classification_label(label_id: int):
        """Delete a classification label by id."""
        labels_ref: ClassificationLabelClient | None = state["labels"]
        if labels_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        loop = asyncio.get_event_loop()
        deleted: bool = await loop.run_in_executor(
            None, lambda: labels_ref.delete_label(label_id)
        )

        if not deleted:
            return Response(
                content=json.dumps({"error": f"Label {label_id} not found"}),
                status_code=404,
                media_type="application/json",
            )

        return {"ok": True, "label_id": label_id}

    # ------------------------------------------------------------------
    # Attribution role-type CRUD endpoints
    # ------------------------------------------------------------------

    @app.get("/api/attribution/role-types", response_model=None)
    async def list_role_types():
        """Return all entity role type definitions."""
        loop = asyncio.get_event_loop()
        role_types_ref: EntityRoleTypeClient | None = state["role_types"]
        if role_types_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        result = await loop.run_in_executor(None, role_types_ref.get_role_types)
        if result is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        return [dataclasses.asdict(rt) for rt in result]

    @app.post("/api/attribution/role-types", response_model=None)
    async def create_role_type(body: CreateRoleType):
        """Create a new entity role type."""
        role_types_ref: EntityRoleTypeClient | None = state["role_types"]
        if role_types_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        loop = asyncio.get_event_loop()
        result: EntityRoleType | None = await loop.run_in_executor(
            None,
            lambda: role_types_ref.create_role_type(body.name, body.description, body.color),
        )

        if result is None:
            # create_role_type returns None on DB error (e.g. duplicate name)
            return Response(
                content=json.dumps({"error": f"Could not create role type '{body.name}'"}),
                status_code=409,
                media_type="application/json",
            )

        return dataclasses.asdict(result)

    @app.patch("/api/attribution/role-types/{role_type_id}", response_model=None)
    async def update_role_type(role_type_id: int, body: UpdateRoleType):
        """Update description, color, and/or enabled flag for a role type."""
        role_types_ref: EntityRoleTypeClient | None = state["role_types"]
        if role_types_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        loop = asyncio.get_event_loop()
        result: EntityRoleType | None = await loop.run_in_executor(
            None,
            lambda: role_types_ref.update_role_type(
                role_type_id,
                description=body.description,
                color=body.color,
                enabled=body.enabled,
            ),
        )

        if result is None:
            return Response(
                content=json.dumps({"error": f"Role type {role_type_id} not found"}),
                status_code=404,
                media_type="application/json",
            )

        return dataclasses.asdict(result)

    @app.delete("/api/attribution/role-types/{role_type_id}", response_model=None)
    async def delete_role_type(role_type_id: int):
        """Delete an entity role type by id."""
        role_types_ref: EntityRoleTypeClient | None = state["role_types"]
        if role_types_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        loop = asyncio.get_event_loop()
        deleted: bool = await loop.run_in_executor(
            None, lambda: role_types_ref.delete_role_type(role_type_id)
        )

        if not deleted:
            return Response(
                content=json.dumps({"error": f"Role type {role_type_id} not found"}),
                status_code=404,
                media_type="application/json",
            )

        return {"ok": True, "role_type_id": role_type_id}

    # ------------------------------------------------------------------
    # Attribution labelling endpoints
    # ------------------------------------------------------------------

    @app.get("/api/attribution/stats", response_model=None)
    async def attribution_stats():
        """Return attribution annotation progress stats."""
        loop = asyncio.get_event_loop()
        articles_ref: ArticleClient | None = state["articles"]
        if articles_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        result = await loop.run_in_executor(None, articles_ref.get_attribution_stats)
        if result is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        return dataclasses.asdict(result)

    @app.get("/api/attribution/articles", response_model=None)
    async def attribution_articles(
        page: int = 1,
        page_size: int = 10,
        filter: str = "all",
        sort_by: str = "date_ingested",
        sort_dir: str = "desc",
    ):
        """Return a paginated list of articles that have entities for annotation."""
        # Validate query parameters against whitelists.
        if filter not in {"all", "annotated", "unannotated", "auto_classified"}:
            return Response(
                content=json.dumps({"error": f"Invalid filter: {filter}"}),
                status_code=422,
                media_type="application/json",
            )
        if sort_by not in {"date_ingested", "source_origin"}:
            return Response(
                content=json.dumps({"error": f"Invalid sort_by: {sort_by}"}),
                status_code=422,
                media_type="application/json",
            )
        if sort_dir not in {"asc", "desc"}:
            return Response(
                content=json.dumps({"error": f"Invalid sort_dir: {sort_dir}"}),
                status_code=422,
                media_type="application/json",
            )

        loop = asyncio.get_event_loop()
        articles_ref: ArticleClient | None = state["articles"]
        if articles_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        result = await loop.run_in_executor(
            None,
            lambda: articles_ref.get_attribution_articles(
                page, min(page_size, 50), filter, sort_by, sort_dir
            ),
        )
        if result is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        return dataclasses.asdict(result)

    @app.patch("/api/attribution/articles/{article_id}/roles", response_model=None)
    async def update_article_roles(article_id: int, body: EntityRoleUpdate):
        """Save entity role assignments for a single article.

        Validates that all supplied role names exist in the entity_role_types table.
        An empty roles dict clears the annotation.
        """
        roles = body.roles

        # Validate role names against the entity_role_types table.
        # This is dynamic — new role types created via the UI are immediately
        # accepted without a service restart.
        loop = asyncio.get_event_loop()
        role_types_ref: EntityRoleTypeClient | None = state["role_types"]
        if role_types_ref is not None and roles:
            db_role_types = await loop.run_in_executor(None, role_types_ref.get_role_types)
            if db_role_types is not None:
                allowed = {rt.name for rt in db_role_types}
                invalid = [role for role in roles.values() if role not in allowed]
                if invalid:
                    return Response(
                        content=json.dumps(
                            {
                                "error": f"Invalid role(s): {', '.join(invalid)}. "
                                f"Allowed: {', '.join(sorted(allowed))}"
                            }
                        ),
                        status_code=422,
                        media_type="application/json",
                    )

        articles_ref: ArticleClient | None = state["articles"]
        if articles_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        found = await loop.run_in_executor(
            None,
            lambda: articles_ref.update_entity_roles(article_id, roles),
        )
        if not found:
            return Response(
                content=json.dumps({"error": f"Article {article_id} not found"}),
                status_code=404,
                media_type="application/json",
            )

        return {"ok": True, "article_id": article_id, "roles": roles}

    # ------------------------------------------------------------------
    # Graph endpoints — relation types CRUD + graph queries
    # ------------------------------------------------------------------

    @app.get("/api/graph/relation-types", response_model=None)
    async def get_relation_types():
        """Return all relation type definitions."""
        loop = asyncio.get_event_loop()
        client: RelationTypeClient | None = state["relation_types"]
        if client is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )
        result = await loop.run_in_executor(None, client.get_relation_types)
        if result is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )
        return [dataclasses.asdict(rt) for rt in result]

    @app.post("/api/graph/relation-types", response_model=None, status_code=201)
    async def create_relation_type(body: CreateRelationType):
        """Create a new relation type."""
        loop = asyncio.get_event_loop()
        client: RelationTypeClient | None = state["relation_types"]
        if client is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )
        result: RelationType | None = await loop.run_in_executor(
            None,
            lambda: client.create_relation_type(
                body.name, body.description, body.color, body.directed
            ),
        )
        if result is None:
            return Response(
                content=json.dumps({"error": f"Could not create relation type '{body.name}'"}),
                status_code=409,
                media_type="application/json",
            )
        return dataclasses.asdict(result)

    @app.patch("/api/graph/relation-types/{relation_type_id}", response_model=None)
    async def update_relation_type(relation_type_id: int, body: UpdateRelationType):
        """Update description, color, directed, and/or enabled flag for a relation type."""
        loop = asyncio.get_event_loop()
        client: RelationTypeClient | None = state["relation_types"]
        if client is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )
        result: RelationType | None = await loop.run_in_executor(
            None,
            lambda: client.update_relation_type(
                relation_type_id,
                description=body.description,
                color=body.color,
                directed=body.directed,
                enabled=body.enabled,
            ),
        )
        if result is None:
            return Response(
                content=json.dumps({"error": f"Relation type {relation_type_id} not found"}),
                status_code=404,
                media_type="application/json",
            )
        return dataclasses.asdict(result)

    @app.delete("/api/graph/relation-types/{relation_type_id}", response_model=None)
    async def delete_relation_type(relation_type_id: int):
        """Delete a relation type by id."""
        loop = asyncio.get_event_loop()
        client: RelationTypeClient | None = state["relation_types"]
        if client is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )
        deleted: bool = await loop.run_in_executor(
            None, lambda: client.delete_relation_type(relation_type_id)
        )
        if not deleted:
            return Response(
                content=json.dumps({"error": f"Relation type {relation_type_id} not found"}),
                status_code=404,
                media_type="application/json",
            )
        return {"ok": True, "relation_type_id": relation_type_id}

    @app.get("/api/graph/relations", response_model=None)
    async def get_graph_relations(
        lambda_decay: float = 0.01,
        min_strength: float = 0.1,
        corroboration: float = 0.5,
        relation_types: str = "",
        limit: int = 200,
    ):
        """Query the relation graph with temporal decay applied.

        The lambda_decay parameter controls how fast edges fade with time:
          - 0.001 → half-life ~29 days (slow fade)
          - 0.01  → half-life ~3 days (moderate fade)
          - 0.1   → half-life ~7 hours (fast fade)

        The corroboration parameter (α) boosts edges mentioned in multiple articles:
          display = base_strength * article_count^α * exp(-λ * hours)
          - 0   → ignore article count
          - 0.5 → square-root scaling (4 articles = 2x boost)
          - 1   → linear scaling

        relation_types is a comma-separated string of type names to filter by.
        Leave empty to include all types.
        """
        loop = asyncio.get_event_loop()
        graph_ref: GraphClient | None = state["graph"]
        if graph_ref is None:
            return Response(
                content=json.dumps({"error": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )

        # Parse the comma-separated filter string into a list, or None for no filter.
        type_filter = [t.strip() for t in relation_types.split(",") if t.strip()] or None

        result = await loop.run_in_executor(
            None,
            lambda: graph_ref.get_graph(
                lambda_decay=lambda_decay,
                min_strength=min_strength,
                corroboration=corroboration,
                relation_types=type_filter,
                limit=min(limit, 500),
            ),
        )
        return result

    return app


def _format_db(stats: DbStats | None) -> dict | None:
    """Convert DbStats to a JSON-serialisable dict.

    We can't use dataclasses.asdict() directly here because datetime objects
    are not JSON-serialisable by default. We format the datetime explicitly.
    """
    if stats is None:
        return None

    latest: str | None = None
    if stats.latest_insert is not None:
        dt: datetime = stats.latest_insert
        # psycopg returns timezone-aware datetimes for TIMESTAMPTZ columns.
        # Naive datetimes (plain TIMESTAMP) are assumed to be UTC.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        latest = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "article_count": stats.article_count,
        "latest_insert": latest,
        "labelled_count": stats.labelled_count,
    }
