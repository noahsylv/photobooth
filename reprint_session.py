#!/usr/bin/env python3
"""Rebuild and optionally print a captured photo session."""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from config import AppConfig
from photo_filters import VALID_FILTERS
from printer import print_image
from strip import create_strip


def find_latest_session(captures_dir: Path) -> Path | None:
    sessions = sorted(
        (path for path in captures_dir.glob("session_*") if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return sessions[0] if sessions else None


def find_session_photos(photos_dir: Path, photo_count: int) -> list[str]:
    photos = sorted(photos_dir.glob("*.jpg"))
    if len(photos) != photo_count:
        raise ValueError(
            f"Expected {photo_count} JPG photos in {photos_dir}, found {len(photos)}."
        )
    return [str(path) for path in photos]


def get_screen_size() -> tuple[int, int]:
    user32 = ctypes.windll.user32
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def show_strip(strip_path: str) -> None:
    with Image.open(strip_path) as img:
        frame = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)

    screen_w, screen_h = get_screen_size()
    max_w = int(screen_w * 0.80)
    max_h = int(screen_h * 0.80)

    height, width = frame.shape[:2]
    scale = min(1.0, max_w / width, max_h / height)
    new_size = (int(width * scale), int(height * scale))
    frame = cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)

    window_name = f"Strip Preview — {Path(strip_path).name}"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, new_size[0], new_size[1])
    cv2.imshow(window_name, frame)
    print("Previewing strip. Press any key to close the window.")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild and optionally print a captured photo session."
    )
    parser.add_argument(
        "--filter",
        choices=VALID_FILTERS,
        help="Filter to apply; defaults to the filter in config.py.",
    )
    parser.add_argument(
        "--session-dir",
        type=Path,
        help="Session directory to use; defaults to the newest session.",
    )
    parser.add_argument(
        "--photos-dir",
        type=Path,
        help=(
            "Arbitrary folder of JPG photos to use instead of a capture session "
            "(overrides --session-dir/--captures-dir)."
        ),
    )
    parser.add_argument(
        "--captures-dir",
        type=Path,
        default=None,
        help="Directory containing sessions; defaults to config.py.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output strip path; defaults to output/reprint_<timestamp>.jpg.",
    )
    parser.add_argument(
        "--final-exposure",
        type=float,
        default=None,
        help="Exposure multiplier for the final filter.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Open a preview window of the rebuilt strip before printing.",
    )
    parser.add_argument(
        "--print",
        dest="should_print",
        action="store_true",
        help="Send the rebuilt strip to the configured printer.",
    )
    parser.add_argument(
        "--no-print",
        dest="should_print",
        action="store_false",
        help="Only rebuild the strip; do not print it (default).",
    )
    parser.set_defaults(should_print=False)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = AppConfig()

    if args.photos_dir is not None:
        source_dir = args.photos_dir
        if not source_dir.is_dir():
            print(f"Photos directory not found: {source_dir}")
            return 1
    else:
        captures_dir = args.captures_dir or config.CAPTURES_DIR
        source_dir = args.session_dir or find_latest_session(captures_dir)
        if source_dir is None:
            print(f"No sessions found in {captures_dir}")
            return 1
        if not source_dir.is_dir():
            print(f"Session directory not found: {source_dir}")
            return 1

    try:
        photo_paths = find_session_photos(source_dir, config.PHOTO_COUNT)
    except ValueError as exc:
        print(exc)
        return 1

    filter_name = args.filter or config.PHOTO_FILTER
    exposure = args.final_exposure
    if exposure is None:
        exposure = config.PHOTO_FILTER_FINAL_EXPOSURE
    reprint_config = replace(
        config,
        PHOTO_FILTER=filter_name,
        PHOTO_FILTER_FINAL_EXPOSURE=exposure,
    )

    output_path = args.output or config.OUTPUT_DIR / (
        f"reprint_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    )
    strip_path = create_strip(photo_paths, str(output_path), reprint_config)
    print(f"Source: {source_dir}")
    print(f"Filter: {filter_name}")
    print(f"Strip saved to: {strip_path}")

    if args.show:
        show_strip(strip_path)

    if args.should_print:
        print_image(
            strip_path,
            printer_name=config.PRINTER_NAME,
            rotation_degrees=config.PRINTER_ROTATION_DEGREES,
        )
        print("Print job submitted.")
    else:
        print("Printing skipped. Use --print to submit this strip.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())