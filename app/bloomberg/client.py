"""Thin wrapper around a blpapi Session.

The Bloomberg Python SDK (``blpapi``) is synchronous and must be installed
from Bloomberg's package index. We open a single long-lived session per
process and serialise access to it through a lock because ``blpapi.Session``
is not safe for concurrent use from multiple threads.

We intentionally import ``blpapi`` lazily so the rest of the project can be
imported (for docs, tests, type checking) on machines without the Bloomberg
SDK or a running Terminal.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Optional

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    import blpapi


class BloombergError(RuntimeError):
    """Raised when the Bloomberg API returns an error or cannot be reached."""


class BloombergClient:
    """Process-wide handle to a blpapi Session."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
        self._session: Optional["blpapi.Session"] = None
        self._lock = threading.Lock()
        self._opened_services: set[str] = set()

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the underlying blpapi session. Idempotent."""
        with self._lock:
            if self._session is not None:
                return
            try:
                import blpapi  # noqa: WPS433 (runtime import)
            except ImportError as exc:  # pragma: no cover
                raise BloombergError(
                    "The 'blpapi' package is not installed. Install it from "
                    "https://blpapi.bloomberg.com/repository/releases/python/simple/"
                ) from exc

            options = blpapi.SessionOptions()
            options.setServerHost(self._settings.bloomberg_host)
            options.setServerPort(self._settings.bloomberg_port)
            options.setAutoRestartOnDisconnection(True)

            logger.info(
                "Starting Bloomberg session against %s:%s",
                self._settings.bloomberg_host,
                self._settings.bloomberg_port,
            )
            session = blpapi.Session(options)
            if not session.start():
                raise BloombergError(
                    "Failed to start Bloomberg session. Is the Terminal "
                    "running and bbcomm reachable?"
                )
            self._session = session

    def stop(self) -> None:
        with self._lock:
            if self._session is not None:
                try:
                    self._session.stop()
                finally:
                    self._session = None
                    self._opened_services.clear()

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    def open_service(self, name: str) -> "blpapi.Service":
        if self._session is None:
            self.start()
        assert self._session is not None
        if name not in self._opened_services:
            if not self._session.openService(name):
                raise BloombergError(f"Failed to open Bloomberg service {name!r}")
            self._opened_services.add(name)
        return self._session.getService(name)

    # ------------------------------------------------------------------
    # Synchronous request/response helper
    # ------------------------------------------------------------------

    def send_request(self, request: "blpapi.Request") -> list["blpapi.Message"]:
        """Send a request and block until the final response has been received.

        Returns the list of response messages. Serialised via ``self._lock``
        because blpapi sessions are not thread-safe.
        """
        import blpapi  # noqa: WPS433

        if self._session is None:
            self.start()
        assert self._session is not None

        with self._lock:
            cid = self._session.sendRequest(request)
            messages: list[blpapi.Message] = []
            while True:
                event = self._session.nextEvent(timeout=30_000)
                event_type = event.eventType()
                for msg in event:
                    # Filter to our correlation id if present
                    if msg.correlationIds() and cid not in msg.correlationIds():
                        continue
                    messages.append(msg)
                if event_type == blpapi.Event.RESPONSE:
                    break
                if event_type == blpapi.Event.TIMEOUT:
                    raise BloombergError("Timed out waiting for Bloomberg response")
            return messages


# ---- Module-level singleton ------------------------------------------------


_client: Optional[BloombergClient] = None
_client_lock = threading.Lock()


def get_client() -> BloombergClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = BloombergClient()
        return _client
