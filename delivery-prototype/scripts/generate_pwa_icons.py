#!/usr/bin/env python3
"""Generate simple PWA icons for field metrics."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "icons"
OUT.mkdir(parents=True, exist_ok=True)


def _draw(size: int, path: Path) -> None:
    img = Image.new("RGB", (size, size), "#3b82f6")
    draw = ImageDraw.Draw(img)
    margin = size // 6
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=size // 8,
        fill="#0f1419",
    )
    draw.text((size * 0.28, size * 0.32), "DL", fill="#e7ecf3")
    img.save(path, format="PNG")


def main() -> None:
    _draw(192, OUT / "metrics-192.png")
    _draw(512, OUT / "metrics-512.png")
    print(f"Wrote icons to {OUT}")


if __name__ == "__main__":
    main()
