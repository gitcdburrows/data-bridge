"""FastAPI application entrypoint for the Bloomberg ↔ Universe Studio bridge."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.bloomberg.client import BloombergError, get_client
from app.config import get_settings
from app.routers import historical, instruments, intraday, reference, stream

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    client = get_client()
    try:
        client.start()
    except BloombergError as exc:
        # Don't crash the app: the HTTP endpoints will return 502 until the
        # Bloomberg Terminal becomes reachable. This lets you launch the
        # bridge before starting the Terminal, which is nicer for dev.
        logger.warning("Bloomberg session not available at startup: %s", exc)
    yield
    client.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Universe Studio ↔ Bloomberg Data Bridge",
        version=__version__,
        summary=(
            "HTTP + WebSocket bridge exposing Bloomberg Terminal data "
            "(blpapi) to the Universe Studio JavaScript explorer."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        client = get_client()
        bloomberg_up = client._session is not None  # noqa: SLF001
        return {
            "status": "ok",
            "version": __version__,
            "bloomberg_connected": bloomberg_up,
        }

    app.include_router(reference.router)
    app.include_router(historical.router)
    app.include_router(intraday.router)
    app.include_router(instruments.router)
    app.include_router(stream.router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_reload,
    )
