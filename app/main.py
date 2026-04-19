"""FastAPI application entrypoint for the Bloomberg ↔ Universe Studio bridge."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.bloomberg.client import BloombergError, get_client
from app.config import get_settings
from app.db.engine import dispose_engine
from app.routers import historical, instruments, intraday, reference, sql, stream

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
    dispose_engine()


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

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        # Date-format failures surface as HTTP 400 with a clear message
        # so the JS client can show a deterministic error. Two shapes
        # count as a date failure:
        #   1. Our ``[YYYYMMDD]``-tagged ``value_error`` from a
        #      ``field_validator`` that invoked ``parse_yyyymmdd_strict``.
        #   2. A ``string_pattern_mismatch`` against the ``^\d{8}$``
        #      pattern (the Field-level constraint on ``YyyymmddDate``).
        # Anything else keeps the standard 422 payload.
        def _is_date_error(e: dict) -> bool:
            msg = str(e.get("msg") or "")
            if "[YYYYMMDD]" in msg:
                return True
            ctx = e.get("ctx") or {}
            if e.get("type") == "string_pattern_mismatch" and (
                ctx.get("pattern") == r"^\d{8}$"
            ):
                return True
            return False

        if any(_is_date_error(e) for e in exc.errors()):
            return JSONResponse(
                status_code=400,
                content={
                    "detail": (
                        "Date fields must be YYYYMMDD strings "
                        "(8 digits, no separators)."
                    ),
                    "errors": [
                        {
                            "loc": list(e.get("loc", [])),
                            "msg": str(e.get("msg", "")).replace(
                                "Value error, ", ""
                            ),
                            "input": e.get("input"),
                        }
                        for e in exc.errors()
                    ],
                },
            )
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        client = get_client()
        bloomberg_up = client._session is not None  # noqa: SLF001
        return {
            "status": "ok",
            "version": __version__,
            "bloomberg_connected": bloomberg_up,
            "database_configured": bool(settings.database_url),
        }

    app.include_router(reference.router)
    app.include_router(historical.router)
    app.include_router(intraday.router)
    app.include_router(instruments.router)
    app.include_router(stream.router)
    app.include_router(sql.router)

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
