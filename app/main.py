"""FastAPI application entrypoint for the Bloomberg ↔ Universe Studio bridge."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app import __version__
from app.bloomberg.client import BloombergError, get_client
from app.config import get_settings
from app.dashboard import DASHBOARD_HTML
from app.routers import historical, instruments, intraday, reference, stream

logger = logging.getLogger(__name__)

# Hosts allowed to call the local-only /admin endpoints from a browser.
# Anything else (e.g. the hosted explorer origin) is rejected so a remote
# page can't restart the bridge via a cross-site request.
_LOCAL_ADMIN_HOSTS = {"localhost", "127.0.0.1", "::1"}


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


def _require_local_origin(origin: str | None = Header(default=None)) -> None:
    """Reject browser calls to /admin/* from non-local origins.

    Requests without an ``Origin`` header (curl, the tray supervisor, etc.)
    are allowed; a browser request only carries one cross-origin.
    """
    if origin is None:
        return
    host = urlsplit(origin).hostname
    if host not in _LOCAL_ADMIN_HOSTS:
        raise HTTPException(status_code=403, detail="Admin endpoints are local-only.")


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
    app.state.started_at = time.time()
    # Set by the runner so /admin/restart can ask uvicorn to exit cleanly.
    app.state.server = None
    app.state.restart_requested = False

    # Explicit allow-list only (never "*"): this bridge can read Bloomberg
    # data, so a wildcard would let any site the user visits call it. The
    # Explorer sends no cookies, so credentials aren't needed.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
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

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard() -> str:
        return DASHBOARD_HTML

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        client = get_client()
        bloomberg_up = client._session is not None  # noqa: SLF001
        return {
            "status": "ok",
            "version": __version__,
            "bloomberg_connected": bloomberg_up,
            "uptime_seconds": round(time.time() - app.state.started_at, 1),
        }

    @app.post("/admin/restart", tags=["meta"])
    async def restart(_: None = Depends(_require_local_origin)) -> dict:
        """Ask the supervisor to restart the server process.

        Sets a flag and asks uvicorn to exit cleanly; the supervising
        process sees the restart exit code and respawns a fresh server.
        Without a supervisor (e.g. ``uvicorn app.main:app``) this simply
        shuts the process down.
        """
        app.state.restart_requested = True
        server = app.state.server
        if server is not None:
            server.should_exit = True
            return {"status": "restarting"}
        return {
            "status": "unsupported",
            "detail": "No supervisor attached; restart the process manually.",
        }

    app.include_router(reference.router)
    app.include_router(historical.router)
    app.include_router(intraday.router)
    app.include_router(instruments.router)
    app.include_router(stream.router)

    return app


app = create_app()


if __name__ == "__main__":
    from app.runner import run_server

    run_server()
