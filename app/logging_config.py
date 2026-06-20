"""Logging setup that survives a windowed (no-console) frozen build.

A PyInstaller ``--windowed`` executable has no console, so ``sys.stdout`` /
``sys.stderr`` can be ``None`` — which crashes libraries that write to them.
We swap in a sink for those and log to a rotating file next to the
executable so the app is debuggable in the field.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

_configured = False


def log_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.getcwd()


def _ensure_std_streams() -> None:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")  # noqa: SIM115


def setup_logging(level: int = logging.INFO) -> str:
    """Configure root logging once. Returns the log file path."""
    global _configured
    _ensure_std_streams()
    log_path = os.path.join(log_dir(), "data-bridge.log")
    if _configured:
        return log_path

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level)

    file_handler = RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Mirror to the console during development (not in a frozen build).
    if not getattr(sys, "frozen", False):
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)

    _configured = True
    return log_path
