#!/usr/bin/env python3
"""Preview which part of a photo the current crop config keeps.

Shows the full, uncropped photo with a box drawn around the region that
would actually end up in the printed strip (accounting for
PHOTO_CROP_TOP_TRIM/BOTTOM_TRIM and PHOTO_CROP_CENTER_X/Y).
"""

from __future__ import annotations

import argparse
import ctypes
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps

from config import AppConfig
from strip import _trim_top_bottom, cover_crop_box, slot_inner_size

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")


def find_photo_by_recency(captures_dir: Path, back: int = 0) -> Path | None:
    """Return a captured photo by recency across all sessions; back=0 is the
    most recent photo, back=1 the 2nd most recent, etc."""
    photos = sorted(
        (
            path
            for path in captures_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not 0 <= back < len(photos):
        return None
    return photos[back]


def get_screen_size() -> tuple[int, int]:
    user32 = ctypes.windll.user32
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def show_preview(img: Image.Image, title: str) -> None:
    frame = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)

    screen_w, screen_h = get_screen_size()
    max_w = int(screen_w * 0.80)
    max_h = int(screen_h * 0.80)

    height, width = frame.shape[:2]
    scale = min(1.0, max_w / width, max_h / height)
    new_size = (int(width * scale), int(height * scale))
    frame = cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)

    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(title, new_size[0], new_size[1])
    cv2.imshow(title, frame)
    print("Previewing crop. Press any key to close the window.")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show the crop box the current config would apply to a photo."
    )
    parser.add_argument(
        "--photo",
        type=Path,
        default=None,
        help="Exact photo path to preview; defaults to the most recent captured photo.",
    )
    parser.add_argument(
        "--back",
        type=int,
        default=0,
        metavar="N",
        help=(
            "Select the Nth most recent captured photo instead of the latest: "
            "0=most recent (default), 1=2nd most recent, 2=3rd most recent, etc."
        ),
    )
    parser.add_argument(
        "--captures-dir",
        type=Path,
        default=None,
        help="Directory containing sessions; defaults to config.py.",
    )
    parser.add_argument(
        "--side",
        choices=("L", "R"),
        default="L",
        help="Which strip side's slot aspect ratio to preview (default: L).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = AppConfig()

    if args.photo is not None:
        photo_path = args.photo
        if not photo_path.is_file():
            print(f"Photo not found: {photo_path}")
            return 1
    else:
        captures_dir = args.captures_dir or config.CAPTURES_DIR
        photo_path = find_photo_by_recency(captures_dir, args.back)
        if photo_path is None:
            print(f"No photos found in {captures_dir}")
            return 1

    with Image.open(photo_path) as src:
        full = ImageOps.exif_transpose(src).convert("RGB")

    trimmed = _trim_top_bottom(full, config.PHOTO_CROP_TOP_TRIM, config.PHOTO_CROP_BOTTOM_TRIM)
    top_offset = min(full.height - 1, max(0, int(full.height * config.PHOTO_CROP_TOP_TRIM)))

    slot_w, slot_h = slot_inner_size(config, args.side)
    box = cover_crop_box(
        trimmed, slot_w, slot_h, (config.PHOTO_CROP_CENTER_X, config.PHOTO_CROP_CENTER_Y)
    )
    x0, y0, x1, y1 = box
    full_box = (x0, y0 + top_offset, x1, y1 + top_offset)

    annotated = full.copy()
    draw = ImageDraw.Draw(annotated)
    line_width = max(3, full.width // 300)
    draw.rectangle(full_box, outline="red", width=line_width)

    print(f"Photo: {photo_path}")
    print(f"Full size: {full.width}x{full.height}")
    print(f"Slot aspect target: {slot_w}x{slot_h}")
    print(f"Crop box (in full-photo coords): {tuple(round(v) for v in full_box)}")

    show_preview(annotated, f"Crop preview — {photo_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
