# Article store service
#
# Build from the project root (so the base Dockerfile is in context):
#   docker build -f services/article-store/Dockerfile -t alexandria-article-store .
#
# Configuration via environment variables:
#   RABBITMQ_URL     - AMQP connection string (required).
#   DATABASE_URL     - PostgreSQL connection string (required).

FROM alexandria-base

# Install dependencies first (cached layer — only re-runs when lockfile changes).
COPY services/article-store/pyproject.toml services/article-store/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Copy source and install the project itself.
COPY services/article-store/src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

USER app
CMD ["uv", "run", "--no-sync", "python", "-m", "article_store"]
