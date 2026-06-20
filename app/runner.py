"""Server ('serve') mode: runs the FastAPI app under uvicorn.

This is the child process launched by the tray supervisor. When the running
server is asked to restart — via ``POST /admin/restart`` or the tray menu —
it exits with :data:`RESTART_EXIT_CODE` so the supervisor knows to respawn a
fresh process rather than treat it as a crash.
"""

from __future__ import annotations

import logging
import sys

from app.config import get_settings
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)

# Distinct, non-crash exit code the supervisor interprets as "respawn me".
RESTART_EXIT_CODE = 3


def run_server() -> None:
    import uvicorn  # local import: the supervisor process never needs uvicorn

    setup_logging()
    settings = get_settings()

    # Import the app after logging is configured so startup logs are captured.
    from app.main import app

    config = uvicorn.Config(
        app,
        host=settings.app_host,
        port=settings.app_port,
        log_config=None,  # use the logging we configured above
        access_log=True,
    )
    server = uvicorn.Server(config)
    app.state.server = server  # lets /admin/restart ask uvicorn to exit

    logger.info(
        "Bloomberg Data Bridge serving on http://%s:%s",
        settings.app_host,
        settings.app_port,
    )
    server.run()

    if getattr(app.state, "restart_requested", False):
        logger.info("Restart requested — exiting with restart code.")
        sys.exit(RESTART_EXIT_CODE)
