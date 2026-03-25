# Article scraper service
#
# Build from the project root (so the base Dockerfile is in context):
#   docker build -f services/article-scraper/Dockerfile -t alexandria-article-scraper .
#
# Configuration via environment variables:
#   RABBITMQ_URL     - AMQP connection string (required).

FROM alexandria-base

# Install dependencies first (cached layer — only re-runs when lockfile changes).
COPY services/article-scraper/pyproject.toml services/article-scraper/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Copy source and install the project itself.
COPY services/article-scraper/src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

USER app
CMD ["uv", "run", "--no-sync", "python", "-m", "article_scraper"]
