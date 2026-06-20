"""Tray supervisor: the default mode when you launch the app.

Runs a system-tray icon that supervises the FastAPI server as a child
process. The icon colour and menu reflect live state (server up/down,
Bloomberg Terminal connected or not), and the menu offers Restart and Quit
plus quick links to the status page and API docs.

Why a child process? Restarting the server cleanly means tearing down the
``uvicorn`` event loop and the ``blpapi`` session and starting fresh. Doing
that from within the same process is fragile; supervising a child lets us
simply terminate and respawn it. The supervisor owns the whole lifecycle in
a single monitor loop so there are no races between auto-restart and the
user clicking Restart.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import urllib.request
import webbrowser

from app.config import get_settings
from app.logging_config import setup_logging
from app.runner import RESTART_EXIT_CODE

logger = logging.getLogger(__name__)

# Tray icon colours (RGBA).
_GREEN = (34, 197, 94, 255)
_AMBER = (245, 158, 11, 255)
_RED = (239, 68, 68, 255)
_GREY = (100, 116, 139, 255)

_HEALTH_POLL_SECONDS = 3
_MAX_BACKOFF_SECONDS = 30


def _make_icon(color):
    from app.icon import render_icon

    return render_icon(64, bg=color)


class Supervisor:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.proc: subprocess.Popen | None = None
        self.icon = None  # pystray.Icon, created in run()

        self._stop = threading.Event()  # set on Quit
        self._restart_requested = False  # set on tray Restart
        self._consecutive_crashes = 0

        # Display state.
        self.server_state = "starting"  # starting | running | restarting | crashed
        self.bloomberg_connected = False

    # ------------------------------------------------------------------
    # URLs / child process
    # ------------------------------------------------------------------

    @property
    def base_url(self) -> str:
        host = self.settings.app_host
        if host in ("0.0.0.0", "::"):  # not browsable — use loopback
            host = "127.0.0.1"
        return f"http://{host}:{self.settings.app_port}"

    def _child_command(self) -> list[str]:
        if getattr(sys, "frozen", False):
            # Re-run this same executable in serve mode.
            return [sys.executable, "--serve"]
        # Dev: re-run the entry script (run.py) with the same interpreter.
        return [sys.executable, os.path.abspath(sys.argv[0]), "--serve"]

    def _spawn(self) -> None:
        cmd = self._child_command()
        creationflags = 0
        if os.name == "nt":
            # Don't flash a console window for the child server.
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        logger.info("Launching server: %s", " ".join(cmd))
        self.proc = subprocess.Popen(cmd, creationflags=creationflags)

    def _terminate_proc(self) -> None:
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("Server did not stop in time; killing it.")
                proc.kill()
        except Exception:  # pragma: no cover - platform specific
            logger.exception("Error terminating server process")

    # ------------------------------------------------------------------
    # Monitor loop (owns the child lifecycle)
    # ------------------------------------------------------------------

    def _monitor(self) -> None:
        while not self._stop.is_set():
            self.server_state = "starting"
            self._refresh()
            try:
                self._spawn()
            except Exception:
                logger.exception("Failed to launch server process")
                self.server_state = "crashed"
                self._refresh()
                if self._stop.wait(5):
                    break
                continue

            code = self.proc.wait()
            if self._stop.is_set():
                break

            if self._restart_requested or code == RESTART_EXIT_CODE:
                self._restart_requested = False
                self._consecutive_crashes = 0
                self.server_state = "restarting"
                self.bloomberg_connected = False
                self._refresh()
                continue

            # Unexpected exit → crash. Back off and retry.
            self._consecutive_crashes += 1
            backoff = min(2 ** self._consecutive_crashes, _MAX_BACKOFF_SECONDS)
            self.server_state = "crashed"
            self.bloomberg_connected = False
            self._refresh()
            logger.warning(
                "Server exited unexpectedly (code=%s). Retrying in %ss.",
                code,
                backoff,
            )
            if self._stop.wait(backoff):
                break

        self._terminate_proc()

    # ------------------------------------------------------------------
    # Health poller (updates Bloomberg-connected state)
    # ------------------------------------------------------------------

    def _poll_health(self) -> None:
        url = self.base_url + "/health"
        while not self._stop.wait(_HEALTH_POLL_SECONDS):
            if self.proc is None or self.proc.poll() is not None:
                continue  # not running; the monitor owns that state
            try:
                with urllib.request.urlopen(url, timeout=2) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                self.bloomberg_connected = bool(data.get("bloomberg_connected"))
                if self.server_state in ("starting", "restarting", "crashed"):
                    self.server_state = "running"
                self._refresh()
            except Exception:
                # Server alive but not answering yet (still booting).
                if self.server_state == "running":
                    self.server_state = "starting"
                    self._refresh()

    # ------------------------------------------------------------------
    # Tray actions
    # ------------------------------------------------------------------

    def restart(self, *_args) -> None:
        logger.info("Restart requested from tray.")
        self._restart_requested = True
        self.server_state = "restarting"
        self._refresh()
        self._terminate_proc()  # monitor wakes, sees the flag, respawns

    def quit(self, *_args) -> None:
        logger.info("Quit requested from tray.")
        self._stop.set()
        self._terminate_proc()
        if self.icon is not None:
            self.icon.stop()

    def _open_dashboard(self, *_args) -> None:
        webbrowser.open(self.base_url + "/")

    def _open_docs(self, *_args) -> None:
        webbrowser.open(self.base_url + "/docs")

    # ------------------------------------------------------------------
    # Presentation
    # ------------------------------------------------------------------

    def _status_visuals(self):
        if self.server_state == "running":
            if self.bloomberg_connected:
                return _GREEN, f"Bloomberg Bridge — connected · {self.base_url}"
            return _AMBER, f"Bloomberg Bridge — Terminal not connected · {self.base_url}"
        if self.server_state in ("starting", "restarting"):
            return _GREY, "Bloomberg Bridge — starting…"
        return _RED, "Bloomberg Bridge — stopped"

    def _status_text(self) -> str:
        if self.server_state == "running":
            return (
                "● Running · Bloomberg connected"
                if self.bloomberg_connected
                else "● Running · Bloomberg not connected"
            )
        if self.server_state == "restarting":
            return "● Restarting…"
        if self.server_state == "starting":
            return "● Starting…"
        return "● Stopped — retrying…"

    def _build_menu(self):
        from pystray import Menu, MenuItem

        from app import autostart

        items = [
            MenuItem(lambda _i: self._status_text(), None, enabled=False),
            MenuItem(lambda _i: self.base_url, None, enabled=False),
            Menu.SEPARATOR,
            MenuItem("Open status page", self._open_dashboard, default=True),
            MenuItem("Open API docs", self._open_docs),
            MenuItem("Restart server", self.restart),
        ]
        if autostart.is_supported():
            items.append(
                MenuItem(
                    "Start on login",
                    self._toggle_autostart,
                    checked=lambda _i: autostart.is_enabled(),
                )
            )
        items += [Menu.SEPARATOR, MenuItem("Quit", self.quit)]
        return Menu(*items)

    def _toggle_autostart(self, icon, _item) -> None:
        from app import autostart

        try:
            enabled = autostart.toggle()
            logger.info("Start-on-login %s", "enabled" if enabled else "disabled")
        except Exception:
            logger.exception("Failed to toggle start-on-login")
        icon.update_menu()

    def _refresh(self) -> None:
        if self.icon is None:
            return
        color, tooltip = self._status_visuals()
        try:
            self.icon.icon = _make_icon(color)
            self.icon.title = tooltip
            self.icon.update_menu()
        except Exception:  # pragma: no cover - backend specific
            logger.debug("Tray refresh failed", exc_info=True)

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        from pystray import Icon

        setup_logging()
        logger.info("Starting Bloomberg Data Bridge supervisor.")

        threading.Thread(target=self._monitor, daemon=True).start()
        threading.Thread(target=self._poll_health, daemon=True).start()

        color, tooltip = self._status_visuals()
        self.icon = Icon(
            "bloomberg_bridge",
            icon=_make_icon(color),
            title=tooltip,
            menu=self._build_menu(),
        )
        # Blocks on the main thread until quit() calls icon.stop().
        self.icon.run()
        logger.info("Supervisor stopped.")


def run_supervisor() -> None:
    Supervisor().run()
