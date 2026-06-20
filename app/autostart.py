"""Per-user 'start on login' management (Windows, no admin required).

Uses the current-user Run key:

    HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run

which launches the app in the user's interactive session at logon — exactly
where the Bloomberg Terminal session and the tray icon live. Writing to HKCU
is a normal user-rights operation, so it never triggers a UAC / admin prompt.
(Machine-wide auto-start via HKLM or a service would need admin *and* would
run in the wrong session, with no Terminal access and no visible tray.)
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)

_APP_NAME = "BloombergBridge"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def is_supported() -> bool:
    """Auto-start via the Run key is a Windows-only feature."""
    return os.name == "nt"


def _launch_command() -> str:
    """The command to register — launches the tray app (no --serve)."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    # Dev: relaunch the entry script with the current interpreter.
    script = os.path.abspath(sys.argv[0] or "run.py")
    return f'"{sys.executable}" "{script}"'


def is_enabled() -> bool:
    if not is_supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _APP_NAME)
        return bool(value)
    except FileNotFoundError:
        return False
    except OSError:
        logger.debug("Could not read autostart key", exc_info=True)
        return False


def enable() -> None:
    if not is_supported():
        raise RuntimeError("Start on login is only supported on Windows.")
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
        winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, _launch_command())


def disable() -> None:
    if not is_supported():
        return
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, _APP_NAME)
    except FileNotFoundError:
        pass  # already absent


def toggle() -> bool:
    """Flip the setting; return the new state (True = will start on login)."""
    if is_enabled():
        disable()
        return False
    enable()
    return True
