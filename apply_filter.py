#!/usr/bin/env python3
"""Apply a named photo filter to the most recent image from the latest session and display the result."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import ctypes

import cv2
import numpy as np
from PIL import Image

from config import AppConfig
from photo_filters import VALID_FILTERS, apply_photo_filter_to_path


def find_latest_session_photo(captures_dir: Path) -> Path | None:
    sessions = sorted(
        (d for d in captures_dir.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    for session in sessions:
        photos = sorted(session.glob("*.jpg"))
        if photos:
            return photos[-1]
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply a photo filter to the most recent capture photo.")
    parser.add_argument(
        "filter",
        choices=VALID_FILTERS,
        help="Filter to apply: none, bw, sepia, vintage, vintage2",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("output/filtered_latest.jpg"),
        help="Output path for the filtered image.",
    )
    parser.add_argument(
        "--captures-dir",
        type=Path,
        default=Path("captures"),
        help="Directory containing capture sessions.",
    )
    parser.add_argument(
        "--final-exposure",
        type=float,
        default=None,
        help="Exposure multiplier for the 'final' filter. Overrides config value.",
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Save the filtered image without opening a display window.",
    )
    return parser.parse_args()


def get_screen_size() -> tuple[int, int]:
    user32 = ctypes.windll.user32
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def show_image(original_path: Path, filtered_path: Path) -> None:
    with Image.open(filtered_path) as img:
        filtered_frame = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)

    with Image.open(original_path) as img:
        original_frame = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)

    screen_w, screen_h = get_screen_size()
    max_w = int(screen_w * 0.60)
    max_h = int(screen_h * 0.70)

    height, width = filtered_frame.shape[:2]
    scale = min(1.0, max_w / width, max_h / height)
    new_size = (int(width * scale), int(height * scale))

    filtered_frame = cv2.resize(filtered_frame, new_size, interpolation=cv2.INTER_AREA)
    original_frame = cv2.resize(original_frame, new_size, interpolation=cv2.INTER_AREA)

    window_name = f"Filtered Photo — {filtered_path.name}"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, new_size[0], new_size[1])

    current_frame = filtered_frame
    showing_filtered = True
    cv2.imshow(window_name, current_frame)
    print(
        f"Showing filtered photo {filtered_path} at {new_size[0]}x{new_size[1]} "
        f"(max {max_w}x{max_h}). Press SPACE to toggle original, Q or ESC to exit."
    )

    while True:
        key = cv2.waitKey(0) & 0xFF
        if key in (ord("q"), ord("Q"), 27):
            break
        if key == 32:  # SPACE
            showing_filtered = not showing_filtered
            current_frame = filtered_frame if showing_filtered else original_frame
            cv2.imshow(window_name, current_frame)

    cv2.destroyAllWindows()


def main() -> int:
    args = parse_args()
    src = find_latest_session_photo(args.captures_dir)
    if src is None:
        print(f"No photos found in {args.captures_dir}")
        return 1

    config = AppConfig()
    out_path = args.output
    exposure_factor = config.PHOTO_FILTER_FINAL_EXPOSURE
    if args.final_exposure is not None:
        exposure_factor = args.final_exposure

    apply_photo_filter_to_path(src, out_path, args.filter, exposure_factor=exposure_factor)
    print(f"Filtered image saved to {out_path}")
    if not args.no_display:
        show_image(src, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
