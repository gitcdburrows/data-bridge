"""Lazy-built SQLAlchemy engine shared by the /sql router."""

from __future__ import annotations

import logging
import threading
from typing import Optional

from sqlalchemy import Engine, create_engine

from app.config import get_settings

logger = logging.getLogger(__name__)


class DatabaseNotConfigured(RuntimeError):
    """Raised when /sql endpoints are hit but DATABASE_URL is empty."""


_engine: Optional[Engine] = None
_engine_lock = threading.Lock()


def get_engine() -> Engine:
    """Return a process-wide SQLAlchemy Engine, creating it on first use."""
    global _engine
    with _engine_lock:
        if _engine is None:
            settings = get_settings()
            if not settings.database_url:
                raise DatabaseNotConfigured(
                    "DATABASE_URL is not set. Configure it in .env to enable "
                    "the /sql endpoints."
                )
            logger.info("Creating SQLAlchemy engine for %s", _redact(settings.database_url))
            _engine = create_engine(
                settings.database_url,
                pool_pre_ping=True,
                future=True,
            )
        return _engine


def dispose_engine() -> None:
    global _engine
    with _engine_lock:
        if _engine is not None:
            _engine.dispose()
            _engine = None


def _redact(url: str) -> str:
    """Best-effort password scrubbing for log output."""
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    creds, host = rest.split("@", 1)
    if ":" in creds:
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"
    return url
