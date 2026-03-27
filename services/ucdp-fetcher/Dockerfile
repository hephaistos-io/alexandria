# UCDP fetcher service
#
# Build from the project root (so the base Dockerfile is in context):
#   docker build -f services/ucdp-fetcher/Dockerfile -t alexandria-ucdp-fetcher .
#
# Run:
#   docker run alexandria-ucdp-fetcher
#
# Configuration via environment variables:
#   RABBITMQ_URL        - AMQP connection string. When unset, logs to stdout.
#   REDIS_URL           - Redis for dedup + scheduling. When unset, in-memory fallback.
#   FETCH_INTERVAL      - Seconds between fetch cycles (default: 604800 = 1 week).
#   UCDP_ACCESS_TOKEN   - API access token for the UCDP GED Candidate API.

FROM alexandria-base

# Install dependencies first (cached layer — only re-runs when lockfile changes).
COPY services/ucdp-fetcher/pyproject.toml services/ucdp-fetcher/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Copy source and install the project itself.
COPY services/ucdp-fetcher/src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

LABEL alexandria.pipeline.outputs="queue:conflict_events.raw" \
      alexandria.pipeline.stores="redis" \
      alexandria.pipeline.icon="crisis_alert"

USER app
# uv run --no-sync skips the dependency check — everything is already
# installed at build time. Without --no-sync, uv tries to write to
# the venv (owned by root) and fails as the non-root app user.
CMD ["uv", "run", "--no-sync", "python", "-m", "ucdp_fetcher"]
