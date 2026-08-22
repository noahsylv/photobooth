#!/usr/bin/env python3
"""Show the latest captured photo from the most recent session."""

from __future__ import annotations

from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image


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


def main() -> int:
    captures_dir = Path("captures")
    src = find_latest_session_photo(captures_dir)
    if src is None:
        print(f"No photos found in {captures_dir}")
        return 1

    with Image.open(src) as img:
        img = img.convert("RGB")
        frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    window_name = f"Latest Photo — {src.name}"
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    cv2.imshow(window_name, frame)
    print(f"Showing {src}. Press any key or close the window to exit.")
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
