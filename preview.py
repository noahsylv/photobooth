#!/usr/bin/env python3
"""
preview.py  --  Live strip layout preview with adjustable config knobs.

Finds the most recent capture session and renders one strip.
Drag the trackbars to tune spacing; the preview refreshes automatically.

  Q / Escape  -- quit and print final config values
  R           -- reload photos from the most recent session
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from config import AppConfig
from strip import _build_single_strip

WINDOW = "Strip Preview  |  Q = quit  |  R = reload photos"
DISPLAY_WIDTH = 440  # px width of the rendered preview (both strips side by side)

_PLACEHOLDER_COLOURS = [
    (200, 155, 155),
    (155, 200, 155),
    (155, 155, 200),
    (200, 200, 155),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_recent_photos(captures_dir: Path, count: int) -> list[Path]:
    """Return up to *count* JPEGs from the most-recently-modified session."""
    sessions = sorted(
        (d for d in captures_dir.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    for session in sessions:
        photos = sorted(session.glob("*.jpg"))
        if photos:
            found = photos[:count]
            print(f"[preview] session : {session.name}  ({len(found)} photo(s))")
            return found
    return []


def _make_placeholders(cfg: AppConfig, tmp: Path) -> None:
    """Write solid-colour placeholder JPEGs for missing photos."""
    for i in range(cfg.PHOTO_COUNT):
        ph = tmp / f"placeholder_{i}.jpg"
        if not ph.exists():
            img = Image.new("RGB", (cfg.STRIP_WIDTH, 400), _PLACEHOLDER_COLOURS[i % 4])
            img.save(str(ph), quality=85)


def _build_paths(photos: list[Path], cfg: AppConfig, tmp: Path) -> list[str]:
    """Return exactly cfg.PHOTO_COUNT path strings, padding with placeholders."""
    _make_placeholders(cfg, tmp)
    result: list[str] = []
    for i in range(cfg.PHOTO_COUNT):
        if i < len(photos):
            result.append(str(photos[i]))
        else:
            result.append(str(tmp / f"placeholder_{i}.jpg"))
    return result


def _render(paths: list[str], cfg: AppConfig) -> np.ndarray:
    """Generate the full two-strip layout and return a scaled BGR array."""
    left_strip  = _build_single_strip(paths, cfg, "L")
    right_strip = _build_single_strip(paths, cfg, "R")

    # Replicate create_strip: strip 1 at left, strip 2 flush against right edge.
    full = Image.new("RGB", (cfg.PRINT_WIDTH, cfg.PRINT_HEIGHT), "white")
    full.paste(left_strip, (0, 0))
    full.paste(right_strip, (cfg.PRINT_WIDTH - cfg.STRIP_WIDTH, 0))

    scale = DISPLAY_WIDTH / full.width
    dh = max(1, int(full.height * scale))
    small = full.resize((DISPLAY_WIDTH, dh), Image.Resampling.LANCZOS)
    frame = cv2.cvtColor(np.array(small), cv2.COLOR_RGB2BGR)

    # Overlay the 2-inch cut line (red dashed) at the strip boundary.
    cut_x = int(cfg.STRIP_WIDTH * scale)
    h = frame.shape[0]
    dash, gap_len = 12, 6
    y = 0
    while y < h:
        y_end = min(y + dash, h)
        cv2.line(frame, (cut_x, y), (cut_x, y_end), (0, 0, 220), 1)
        y += dash + gap_len

    return frame


def _print_cfg(cfg: AppConfig) -> None:
    line = (
        f"OUTER={cfg.MARGIN_OUTER}  INNER={cfg.MARGIN_INNER}  "
        f"TOP={cfg.MARGIN_TOP}  BOT={cfg.MARGIN_BOTTOM}  "
        f"GAP={cfg.PHOTO_GAP}  FOOTER={cfg.FOOTER_HEIGHT}  "
        f"BORDER={cfg.PHOTO_BORDER}  FONT={cfg.FOOTER_FONT_SIZE}  "
        f"[STRIP_WIDTH={cfg.STRIP_WIDTH}]"
    )
    print(f"\r[config] {line}          ", end="", flush=True)


# ---------------------------------------------------------------------------
# Trackbar spec: (window_label, config_attr, min_val, max_val)
# ---------------------------------------------------------------------------
TRACKBARS: list[tuple[str, str, int, int]] = [
    ("Margin Outer",  "MARGIN_OUTER",     0, 150),
    ("Margin Inner",  "MARGIN_INNER",     0, 150),
    ("Margin Top",    "MARGIN_TOP",       0, 150),
    ("Margin Bottom", "MARGIN_BOTTOM",    0, 150),
    ("Photo Gap",     "PHOTO_GAP",        0,  50),
    ("Footer Height", "FOOTER_HEIGHT",   20, 250),
    ("Photo Border",  "PHOTO_BORDER",     0,  20),
    ("Footer Font",   "FOOTER_FONT_SIZE", 8, 100),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    captures_dir = Path("captures")
    cfg = AppConfig()

    tmp = Path(tempfile.mkdtemp(prefix="pb_preview_"))
    try:
        photos: list[Path] = []
        if captures_dir.exists():
            photos = _find_recent_photos(captures_dir, cfg.PHOTO_COUNT)
        if not photos:
            print("[preview] No session photos found — using colour placeholders.")

        paths = _build_paths(photos, cfg, tmp)
        frame = _render(paths, cfg)

        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        # Size the window: strip preview width + some padding, plus room for trackbars
        cv2.resizeWindow(WINDOW, DISPLAY_WIDTH + 40, frame.shape[0] + len(TRACKBARS) * 30 + 60)
        cv2.imshow(WINDOW, frame)

        for label, attr, min_val, max_val in TRACKBARS:
            initial = max(min_val, min(max_val, getattr(cfg, attr)))
            cv2.createTrackbar(label, WINDOW, initial, max_val, lambda _: None)

        last_values: dict[str, int] = {attr: getattr(cfg, attr) for _, attr, _, _ in TRACKBARS}

        print("[preview] Trackbars ready — drag to adjust, preview updates live.")
        print("[preview] Press Q or Escape to quit.  Press R to reload latest photos.\n")
        _print_cfg(cfg)

        while True:
            key = cv2.waitKey(100) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                break
            if key in (ord("r"), ord("R")):
                if captures_dir.exists():
                    photos = _find_recent_photos(captures_dir, cfg.PHOTO_COUNT)
                paths = _build_paths(photos, cfg, tmp)
                frame = _render(paths, cfg)
                cv2.imshow(WINDOW, frame)

            current: dict[str, int] = {}
            for label, attr, min_val, _ in TRACKBARS:
                raw = cv2.getTrackbarPos(label, WINDOW)
                current[attr] = max(min_val, raw)

            if current != last_values:
                last_values = current.copy()
                try:
                    cfg = replace(cfg, **current)
                    frame = _render(paths, cfg)
                    cv2.imshow(WINDOW, frame)
                    _print_cfg(cfg)
                except Exception as exc:
                    print(f"\n[preview] render error: {exc}")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        cv2.destroyAllWindows()

    print("\n\n[preview] Final values — copy into config.py to keep them:\n")
    for _, attr, _, _ in TRACKBARS:
        print(f"    {attr}: int = {getattr(cfg, attr)}")


if __name__ == "__main__":
    main()
