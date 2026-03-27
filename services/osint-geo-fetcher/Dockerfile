# OSINT geo-fetcher service
#
# Build from the project root (so the base Dockerfile is in context):
#   docker build -f services/osint-geo-fetcher/Dockerfile -t alexandria-osint-geo-fetcher .
#
# Run:
#   docker run alexandria-osint-geo-fetcher
#
# Configuration via environment variables:
#   RABBITMQ_URL     - AMQP connection string. When unset, logs to stdout.
#   REDIS_URL        - Redis for dedup + scheduling. When unset, in-memory fallback.
#   FETCH_INTERVAL   - Seconds between fetch cycles (default: 10800 = 3 hours).

FROM alexandria-base

# Install dependencies first (cached layer — only re-runs when lockfile changes).
COPY services/osint-geo-fetcher/pyproject.toml services/osint-geo-fetcher/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Copy source and install the project itself.
COPY services/osint-geo-fetcher/src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

LABEL alexandria.pipeline.outputs="queue:conflict_events.raw" \
      alexandria.pipeline.stores="redis" \
      alexandria.pipeline.icon="crisis_alert"

USER app
# uv run --no-sync skips the dependency check — everything is already
# installed at build time. Without --no-sync, uv tries to write to
# the venv (owned by root) and fails as the non-root app user.
CMD ["uv", "run", "--no-sync", "python", "-m", "osint_geo_fetcher"]
