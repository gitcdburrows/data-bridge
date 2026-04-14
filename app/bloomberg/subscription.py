"""Real-time market data subscriptions bridged over a WebSocket.

Each WebSocket client gets its own dedicated blpapi.Session running in
``SubscriptionEventHandler`` mode, so Bloomberg can push MarketDataEvents
asynchronously on a background thread. We fan the events into an asyncio
queue so the FastAPI WebSocket handler can consume them from the event loop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from app.bloomberg.client import BloombergError
from app.config import get_settings

logger = logging.getLogger(__name__)


class SubscriptionStream:
    """Bridge a blpapi subscription session onto an asyncio.Queue."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._session = None
        self._topic_by_cid: Dict[int, str] = {}
        self._next_cid = 1

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        try:
            import blpapi  # noqa: WPS433
        except ImportError as exc:  # pragma: no cover
            raise BloombergError(
                "The 'blpapi' package is not installed. Install it from "
                "https://blpapi.bloomberg.com/repository/releases/python/simple/"
            ) from exc

        settings = get_settings()
        options = blpapi.SessionOptions()
        options.setServerHost(settings.bloomberg_host)
        options.setServerPort(settings.bloomberg_port)
        options.setAutoRestartOnDisconnection(True)

        session = blpapi.Session(options, self._dispatch_event)
        if not session.startAsync():
            raise BloombergError("Failed to start async Bloomberg session")
        self._session = session

    def stop(self) -> None:
        if self._session is not None:
            try:
                self._session.stop()
            finally:
                self._session = None

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def subscribe(self, securities: List[str], fields: List[str]) -> None:
        import blpapi  # noqa: WPS433

        if self._session is None:
            raise BloombergError("Subscription session is not started")
        if not self._session.openService("//blp/mktdata"):
            raise BloombergError("Failed to open //blp/mktdata service")

        sub_list = blpapi.SubscriptionList()
        field_spec = ",".join(fields)
        for sec in securities:
            cid_value = self._next_cid
            self._next_cid += 1
            cid = blpapi.CorrelationId(cid_value)
            self._topic_by_cid[cid_value] = sec
            sub_list.add(sec, field_spec, "", cid)
        self._session.subscribe(sub_list)

    # ------------------------------------------------------------------
    # Async consumer
    # ------------------------------------------------------------------

    async def events(self):
        while True:
            yield await self._queue.get()

    # ------------------------------------------------------------------
    # blpapi callback (runs on a background thread)
    # ------------------------------------------------------------------

    def _dispatch_event(self, event, session) -> None:  # noqa: ARG002
        try:
            import blpapi  # noqa: WPS433
        except ImportError:  # pragma: no cover
            return

        try:
            for msg in event:
                payload = self._message_to_dict(msg, event.eventType())
                if payload is not None:
                    self._loop.call_soon_threadsafe(self._queue.put_nowait, payload)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Error dispatching Bloomberg event: %s", exc)

    def _message_to_dict(self, msg, event_type) -> Optional[Dict[str, Any]]:
        import blpapi  # noqa: WPS433
        from app.bloomberg.service import _element_to_py  # noqa: WPS433

        topic: Optional[str] = None
        cids = msg.correlationIds()
        if cids:
            topic = self._topic_by_cid.get(cids[0].value())

        if event_type == blpapi.Event.SUBSCRIPTION_DATA:
            fields: Dict[str, Any] = {}
            for i in range(msg.numElements()):
                child = msg.getElement(i)
                fields[str(child.name())] = _element_to_py(child)
            return {"type": "data", "security": topic, "fields": fields}

        if event_type == blpapi.Event.SUBSCRIPTION_STATUS:
            return {
                "type": "status",
                "security": topic,
                "message_type": str(msg.messageType()),
            }

        if event_type in (blpapi.Event.SESSION_STATUS, blpapi.Event.SERVICE_STATUS):
            return {"type": "session", "message_type": str(msg.messageType())}

        return None
