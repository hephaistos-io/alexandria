# Role classifier service — zero-shot entity role classification via transformers
#
# Build from the project root (so the base Dockerfile is in context):
#   docker build -f services/role-classifier/Dockerfile -t alexandria-role-classifier .
#
# Configuration via environment variables:
#   RABBITMQ_URL   - AMQP connection string (required).
#   DATABASE_URL   - PostgreSQL connection string (required).
#   LABEL_REFRESH  - Seconds between DB role type reloads (default: 300).

FROM alexandria-base

# Install dependencies first (cached layer — only re-runs when lockfile changes).
COPY services/role-classifier/pyproject.toml services/role-classifier/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Copy source and install the project itself.
COPY services/role-classifier/src/ src/
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
CMD ["uv", "run", "--no-sync", "python", "-m", "role_classifier"]
