# Entity resolver service
#
# Build from the project root:
#   docker build -f services/entity-resolver/Dockerfile -t alexandria-entity-resolver .
#
# Configuration via environment variables:
#   RABBITMQ_URL            - AMQP connection string (required).
#   REDIS_URL               - Redis connection string (required).
#   WIKIDATA_API_TOKEN      - Personal API token from api.wikimedia.org (optional).
#   WIKIDATA_CLIENT_ID      - OAuth2 client ID (optional, alternative to token).
#   WIKIDATA_CLIENT_SECRET  - OAuth2 client secret (optional, paired with ID).
#   Authentication priority: API token > OAuth2 > unauthenticated (~500 req/hr).
#   Either method gives 5,000 req/hr authenticated access.

FROM alexandria-base

# Install dependencies first (cached layer — only re-runs when lockfile changes).
COPY services/entity-resolver/pyproject.toml services/entity-resolver/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Copy source, data, and install the project itself.
COPY services/entity-resolver/src/ src/
COPY services/entity-resolver/data/ data/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

USER app
CMD ["uv", "run", "--no-sync", "python", "-m", "entity_resolver"]
