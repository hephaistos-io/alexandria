# Alexandria base image — Python 3.13 + uv
#
# Provides the shared foundation for all Alexandria services.
# Service-specific Dockerfiles extend this with their own dependencies.
#
# Build from the project root:
#   docker build -f docker/base.Dockerfile -t alexandria-base .

FROM python:3.13-slim AS base

# Pin uv version for reproducible builds. Bump this deliberately, not via :latest.
COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /uvx /bin/

# Compile Python bytecode at install time — slower build, faster startup.
ENV UV_COMPILE_BYTECODE=1

# Disable stdout/stderr buffering so log lines appear immediately in
# `docker compose logs`. Without this, Python buffers output when it
# detects a non-TTY (which is the case inside containers).
ENV PYTHONUNBUFFERED=1

# Copy packages instead of symlinking, so the cache mount can live on
# a different filesystem without breaking things.
ENV UV_LINK_MODE=copy

# Don't install dev dependencies (pytest, ruff) in the final image.
ENV UV_NO_DEV=1

# Create a non-root user. Running containers as root is a security risk —
# if an attacker escapes the app, they shouldn't land as root in the container.
RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app
