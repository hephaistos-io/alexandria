# Monitoring API service
#
# Build from the project root (so the base Dockerfile is in context):
#   docker build -f services/monitoring-api/Dockerfile -t alexandria-monitoring-api .
#
# Configuration via environment variables:
#   DATABASE_URL              - PostgreSQL connection string.
#   RABBITMQ_MANAGEMENT_URL   - RabbitMQ Management API base URL (default: http://rabbitmq:15672).
#   RABBITMQ_USER             - RabbitMQ username (default: guest).
#   RABBITMQ_PASSWORD         - RabbitMQ password (default: guest).
#   COMPOSE_PROJECT_NAME      - Docker Compose project label to filter (default: alexandria).

FROM alexandria-base

# Install dependencies first (cached layer — only re-runs when lockfile changes).
COPY services/monitoring-api/pyproject.toml services/monitoring-api/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Copy source and install the project itself.
COPY services/monitoring-api/src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# NOTE: Unlike other services, we do NOT switch to USER app here.
# The Docker socket (/var/run/docker.sock) is owned by root — the app user
# can't read it. This service needs root to query container status.
# The socket is mounted read-only (:ro) so the risk is limited.
CMD ["uv", "run", "--no-sync", "python", "-m", "monitoring_api"]
