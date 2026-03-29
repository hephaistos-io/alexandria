# Event detector service
#
# Build from the project root:
#   docker build -f services/event-detector/Dockerfile -t alexandria-event-detector .
#
# Configuration via environment variables:
#   DATABASE_URL        - PostgreSQL connection string (required).
#   REDIS_URL           - Redis for scheduling. When unset, runs immediately every cycle.
#   DETECTION_INTERVAL  - Seconds between detection cycles (default: 300 = 5 minutes).

FROM alexandria-base

# Install dependencies first (cached layer — only re-runs when lockfile changes).
COPY services/event-detector/pyproject.toml services/event-detector/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Copy source and install the project itself.
COPY services/event-detector/src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

LABEL alexandria.pipeline.inputs="db:articles,db:conflict_events" \
      alexandria.pipeline.outputs="db:events" \
      alexandria.pipeline.stores="redis" \
      alexandria.pipeline.icon="hub"

USER app
CMD ["uv", "run", "--no-sync", "python", "-m", "event_detector"]
