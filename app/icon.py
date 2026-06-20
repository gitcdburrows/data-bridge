"""Programmatic app icon, shared by the tray and the packaged executable.

Drawing it in code keeps the tray icon and the .exe icon visually identical
and lets the tray tint the background by status (green/amber/red/grey)
without shipping a sprite sheet of PNGs. ``scripts/make_icon.py`` renders the
status-neutral brand version to ``assets/icon.ico`` for PyInstaller.

The mark is a rounded "tile" with a small three-bar chart — legible down to
16px and on-theme for market data.
"""

from __future__ import annotations

# Status-neutral brand background for the static .exe / .ico.
BRAND_BG = (37, 99, 235, 255)  # blue-600
FG = (255, 255, 255, 255)


def render_icon(size: int = 256, bg=BRAND_BG, fg=FG):
    """Return a PIL ``Image`` of the app icon at ``size`` px."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = max(1, round(size * 0.06))
    radius = max(1, round(size * 0.22))
    draw.rounded_rectangle(
        (margin, margin, size - 1 - margin, size - 1 - margin),
        radius=radius,
        fill=bg,
    )

    # Three-bar chart inside the tile, bottoms aligned.
    inner = size - 2 * margin
    pad = inner * 0.22
    left = margin + pad
    right = size - margin - pad
    bottom = size - margin - pad
    region_h = bottom - (margin + pad)

    n = 3
    gap = (right - left) * 0.12
    bar_w = ((right - left) - (n - 1) * gap) / n
    bar_radius = max(1, round(bar_w * 0.28))
    heights = (0.45, 0.78, 0.60)

    for i, h in enumerate(heights):
        bx = left + i * (bar_w + gap)
        top = bottom - region_h * h
        draw.rounded_rectangle((bx, top, bx + bar_w, bottom), radius=bar_radius, fill=fg)

    return img
