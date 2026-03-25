# Article fetcher service
#
# Build from the project root (so the base Dockerfile is in context):
#   docker build -f services/article-fetcher/Dockerfile -t alexandria-article-fetcher .
#
# Run:
#   docker run alexandria-article-fetcher
#
# Configuration via environment variables:
#   RABBITMQ_URL     - AMQP connection string. When unset, logs to stdout.
#   FETCH_INTERVAL   - Seconds between fetch cycles (default: 900).

FROM alexandria-base

# Install dependencies first (cached layer — only re-runs when lockfile changes).
COPY services/article-fetcher/pyproject.toml services/article-fetcher/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Copy source and install the project itself.
COPY services/article-fetcher/src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Default pipeline labels — shared by every fetcher instance.
# Compose only needs to set alexandria.pipeline.label (the display name).
LABEL alexandria.pipeline.outputs="queue:articles.rss" \
      alexandria.pipeline.stores="redis" \
      alexandria.pipeline.icon="rss_feed"

USER app
# uv run --no-sync skips the dependency check — everything is already
# installed at build time. Without --no-sync, uv tries to write to
# the venv (owned by root) and fails as the non-root app user.
CMD ["uv", "run", "--no-sync", "python", "-m", "article_fetcher"]
