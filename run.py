"""Entry point for the Bloomberg Data Bridge app.

This is the script PyInstaller freezes into the executable.

    bridge            -> launch the tray supervisor (the app UI)
    bridge --serve    -> run the FastAPI server (the supervised child)

Running with no arguments starts the tray app; the supervisor relaunches
this same executable with ``--serve`` to run the actual server.
"""

from __future__ import annotations

import sys


def main() -> None:
    if "--serve" in sys.argv[1:]:
        from app.runner import run_server

        run_server()
    else:
        from app.supervisor import run_supervisor

        run_supervisor()


if __name__ == "__main__":
    main()
