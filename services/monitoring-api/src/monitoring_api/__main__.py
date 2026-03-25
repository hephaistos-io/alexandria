"""Entry point for running monitoring-api as a module.

Usage:
    uv run python -m monitoring_api

Configuration via environment variables:
    DATABASE_URL              - PostgreSQL connection string.
    RABBITMQ_MANAGEMENT_URL   - RabbitMQ Management API base URL (default: http://rabbitmq:15672).
    RABBITMQ_USER             - RabbitMQ username (default: guest).
    RABBITMQ_PASSWORD         - RabbitMQ password (default: guest).
    COMPOSE_PROJECT_NAME      - Docker Compose project label to filter (default: alexandria).
"""

import json
import logging
import sys
from datetime import datetime, timezone

import uvicorn

from monitoring_api.server import create_app


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects for structured logging."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        entry = {
            "ts": ts,
            "level": record.levelname.lower(),
            "service": self._service,
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(entry)


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(JsonFormatter("monitoring-api"))
logging.root.setLevel(logging.INFO)
logging.root.addHandler(_handler)

app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
