"""Render the brand icon to assets/icon.ico and assets/icon.png.

Run when the mark changes:

    python scripts/make_icon.py

The committed assets are what PyInstaller embeds into the executable, so the
build doesn't need to run this.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from app.icon import render_icon  # noqa: E402

ASSETS = os.path.join(_ROOT, "assets")
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> None:
    os.makedirs(ASSETS, exist_ok=True)
    base = render_icon(256)
    base.save(os.path.join(ASSETS, "icon.png"))
    base.save(os.path.join(ASSETS, "icon.ico"), sizes=ICO_SIZES)
    print(f"Wrote {os.path.join(ASSETS, 'icon.ico')} and icon.png")


if __name__ == "__main__":
    main()
