# GDELT fetcher service
#
# Build from the project root (so the base Dockerfile is in context):
#   docker build -f services/gdelt-fetcher/Dockerfile -t alexandria-gdelt-fetcher .
#
# Configuration via environment variables:
#   RABBITMQ_URL     - AMQP connection string. When unset, logs to stdout.
#   REDIS_URL        - Redis for dedup + scheduling. When unset, in-memory fallback.
#   FETCH_INTERVAL   - Seconds between fetch cycles (default: 900 = 15 minutes).

FROM alexandria-base

# Install dependencies first (cached layer — only re-runs when lockfile changes).
COPY services/gdelt-fetcher/pyproject.toml services/gdelt-fetcher/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Copy source and install the project itself.
COPY services/gdelt-fetcher/src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

LABEL alexandria.pipeline.outputs="queue:conflict_events.raw" \
      alexandria.pipeline.stores="redis" \
      alexandria.pipeline.icon="public"

USER app
CMD ["uv", "run", "--no-sync", "python", "-m", "gdelt_fetcher"]
