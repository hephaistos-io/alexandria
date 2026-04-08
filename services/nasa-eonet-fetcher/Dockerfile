# NASA EONET fetcher service
#
# Build from the project root (so the base Dockerfile is in context):
#   docker build -f services/nasa-eonet-fetcher/Dockerfile -t alexandria-nasa-eonet-fetcher .
#
# Run:
#   docker run alexandria-nasa-eonet-fetcher
#
# Configuration via environment variables:
#   RABBITMQ_URL    - AMQP connection string. When unset, logs to stdout.
#   REDIS_URL       - Redis for dedup + scheduling. When unset, in-memory fallback.
#   FETCH_INTERVAL  - Seconds between fetch cycles (default: 1800 = 30 min).
#                     EONET updates a few times per day; 30 min is more than enough
#                     and gentle on the free upstream API.

FROM alexandria-base

# Install dependencies first (cached layer — only re-runs when lockfile changes).
COPY services/nasa-eonet-fetcher/pyproject.toml services/nasa-eonet-fetcher/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Copy source and install the project itself.
COPY services/nasa-eonet-fetcher/src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

LABEL alexandria.pipeline.outputs="queue:natural_disasters.raw" \
      alexandria.pipeline.stores="redis" \
      alexandria.pipeline.icon="local_fire_department"

USER app
# uv run --no-sync skips the dependency check — everything is already
# installed at build time. Without --no-sync, uv tries to write to
# the venv (owned by root) and fails as the non-root app user.
CMD ["uv", "run", "--no-sync", "python", "-m", "nasa_eonet_fetcher"]
