"""Shared structured logging formatter."""

import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        message = record.getMessage()
        if record.exc_info and record.exc_info[1] is not None:
            message += "\n" + self.formatException(record.exc_info)
        entry = {
            "ts": ts,
            "level": record.levelname.lower(),
            "service": self._service,
            "logger": record.name,
            "message": message,
        }
        return json.dumps(entry)
