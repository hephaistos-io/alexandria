# NER tagger service
#
# Build from the project root (so the base Dockerfile is in context):
#   docker build -f services/ner-tagger/Dockerfile -t alexandria-ner-tagger .
#
# Configuration via environment variables:
#   RABBITMQ_URL     - AMQP connection string (required).

FROM alexandria-base

# Install dependencies first (cached layer — only re-runs when lockfile changes).
COPY services/ner-tagger/pyproject.toml services/ner-tagger/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Copy source and install the project itself.
COPY services/ner-tagger/src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Download spaCy model AFTER uv sync — must come last because uv sync
# removes packages not in the lockfile. We use `uv pip install` because
# `spacy download` shells out to pip, which uv doesn't include.
# Model version must match spaCy major.minor (3.8.x → en_core_web_sm-3.8.0).
RUN uv pip install "en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"

USER app
CMD ["uv", "run", "--no-sync", "python", "-m", "ner_tagger"]
