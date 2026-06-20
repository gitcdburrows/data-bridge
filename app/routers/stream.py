"""/stream WebSocket — real-time market data bridged to the JS client.

Protocol (JSON messages):

    client  ->  server : {"action": "subscribe",
                          "securities": ["IBM US Equity"],
                          "fields": ["LAST_PRICE", "BID", "ASK"]}

    server  ->  client : {"type": "data",
                          "security": "IBM US Equity",
                          "fields": {"LAST_PRICE": 123.45, ...}}

    server  ->  client : {"type": "status", ...}
    server  ->  client : {"type": "error", "detail": "..."}
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.bloomberg.client import BloombergError
from app.bloomberg.subscription import SubscriptionStream

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stream"])


@router.websocket("/stream")
async def stream(websocket: WebSocket) -> None:
    await websocket.accept()
    loop = asyncio.get_running_loop()
    stream_handle = SubscriptionStream(loop)

    try:
        try:
            stream_handle.start()
        except BloombergError as exc:
            await websocket.send_json({"type": "error", "detail": str(exc)})
            await websocket.close()
            return

        pump_task = asyncio.create_task(_pump_events(websocket, stream_handle))

        try:
            while True:
                message = await websocket.receive_json()
                action = message.get("action")
                if action == "subscribe":
                    securities = message.get("securities") or []
                    fields = message.get("fields") or ["LAST_PRICE"]
                    if not securities:
                        await websocket.send_json(
                            {"type": "error", "detail": "No securities supplied"}
                        )
                        continue
                    try:
                        stream_handle.subscribe(securities, fields)
                        await websocket.send_json(
                            {"type": "subscribed", "securities": securities, "fields": fields}
                        )
                    except BloombergError as exc:
                        await websocket.send_json({"type": "error", "detail": str(exc)})
                elif action == "ping":
                    await websocket.send_json({"type": "pong"})
                else:
                    await websocket.send_json(
                        {"type": "error", "detail": f"Unknown action: {action!r}"}
                    )
        except WebSocketDisconnect:
            pass
        finally:
            pump_task.cancel()
            try:
                await pump_task
            except (asyncio.CancelledError, Exception):
                pass
    finally:
        stream_handle.stop()


async def _pump_events(websocket: WebSocket, stream_handle: SubscriptionStream) -> None:
    async for event in stream_handle.events():
        try:
            await websocket.send_json(event)
        except Exception:
            break
