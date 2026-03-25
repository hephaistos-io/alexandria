# Topic tagger service — zero-shot classification via transformers
#
# Build from the project root (so the base Dockerfile is in context):
#   docker build -f services/topic-tagger/Dockerfile -t alexandria-topic-tagger .
#
# Configuration via environment variables:
#   RABBITMQ_URL   - AMQP connection string (required).
#   DATABASE_URL   - PostgreSQL connection string (required).
#   THRESHOLD      - Min score to emit a label (default: 0.3).
#   LABEL_REFRESH  - Seconds between DB label reloads (default: 300).

FROM alexandria-base

# Install dependencies first (cached layer — only re-runs when lockfile changes).
COPY services/topic-tagger/pyproject.toml services/topic-tagger/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Copy source and install the project itself.
COPY services/topic-tagger/src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Pre-download the Hugging Face model weights into the image layer.
# This avoids downloading ~300MB at container startup in production.
# HF_HOME is set explicitly so the cache is visible to the non-root `app`
# user at runtime (the default /root/.cache isn't readable by `app`).
ENV HF_HOME=/app/.hf_cache
RUN uv run --no-sync python -c "\
from transformers import pipeline; \
pipeline('zero-shot-classification', model='MoritzLaurer/deberta-v3-base-zeroshot-v2.0')" \
    && chmod -R a+rX /app/.hf_cache

USER app
CMD ["uv", "run", "--no-sync", "python", "-m", "topic_tagger"]
