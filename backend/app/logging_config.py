"""
Purpose: Configures privacy-safe structured terminal logs for API, MongoDB,
upload, AI, and assessment performance analysis across the demo backend.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any


class JsonTerminalFormatter(logging.Formatter):
    """Formats each optimization event as one searchable JSON terminal line."""

    # Converts a log record into stable JSON without exposing arbitrary payload values.
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "event_fields", {}))
        return json.dumps(payload, ensure_ascii=True, default=str, separators=(",", ":"))


# Installs one process-wide terminal handler at the configured verbosity.
def configure_logging() -> None:
    """Configure application logging once while leaving third-party noise at warning level."""
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    root = logging.getLogger()
    if not any(getattr(handler, "vendor_trust_handler", False) for handler in root.handlers):
        handler = logging.StreamHandler()
        handler.vendor_trust_handler = True
        handler.setFormatter(JsonTerminalFormatter())
        root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)


# Emits one named event with explicitly selected, non-sensitive metrics.
def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields: Any) -> None:
    """Write a structured event while callers control the privacy-safe fields included."""
    logger.log(level, event, extra={"event_fields": fields})
