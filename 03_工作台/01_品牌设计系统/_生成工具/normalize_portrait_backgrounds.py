"""Remove baked-in neutral checkerboards around generated transparent portraits."""

from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PORTRAITS = ROOT / "人物头像" / "正式头像"
CHARACTERS = (
    "xiaoshen",
    "xiaoxi",
    "xiaochai",
    "xiaojing",
    "xiaoce",
    "xiaoxie",
    "xiaotu",
    "xiaoshu",
    "xiaojian",
    "xiaofa",
)


def is_checker_pixel(red: int, green: int, blue: int, alpha: int) -> bool:
    """Only treat bright, low-saturation edge pixels as background."""
    return alpha > 0 and max(red, green, blue) - min(red, green, blue) < 10 and min(red, green, blue) > 205


def clear_checkerboard(source: Path, destination: Path) -> None:
    image = Image.open(source).convert("RGBA")
    pixels = image.load()
    width, height = image.size
    pending = deque()
    seen: set[tuple[int, int]] = set()

    for x in range(width):
        pending.extend(((x, 0), (x, height - 1)))
    for y in range(height):
        pending.extend(((0, y), (width - 1, y)))

    while pending:
        x, y = pending.popleft()
        if (x, y) in seen:
            continue
        seen.add((x, y))
        if not is_checker_pixel(*pixels[x, y]):
            continue
        pixels[x, y] = (0, 0, 0, 0)
        for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            nx, ny = neighbor
            if 0 <= nx < width and 0 <= ny < height and neighbor not in seen:
                pending.append(neighbor)

    image.save(destination, "PNG")


for character in CHARACTERS:
    clear_checkerboard(PORTRAITS / f"{character}-v3.png", PORTRAITS / f"{character}-v4.png")
