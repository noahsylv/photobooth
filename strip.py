from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from config import AppConfig


def create_strip(
    photo_paths: list[str],
    output_path: str,
    config: AppConfig,
) -> str:
    if len(photo_paths) != config.PHOTO_COUNT:
        raise ValueError(f"Expected {config.PHOTO_COUNT} photos, got {len(photo_paths)}.")

    left_strip  = _build_single_strip(photo_paths, config, "L")
    right_strip = _build_single_strip(photo_paths, config, "R") if config.STRIP_LABEL else left_strip

    final_img = Image.new("RGB", (config.PRINT_WIDTH, config.PRINT_HEIGHT), "white")
    final_img.paste(left_strip, (0, 0))
    # Place the second strip flush against the right edge so the gap between
    # the two strips lands exactly on the 2-inch cut line.
    final_img.paste(right_strip, (config.PRINT_WIDTH - config.STRIP_WIDTH, 0))

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    final_img.save(out_path, quality=95)
    return str(out_path)


def _build_single_strip(photo_paths: list[str], config: AppConfig, side: str = "") -> Image.Image:
    strip = Image.new("RGB", (config.STRIP_WIDTH, config.STRIP_HEIGHT), "white")
    draw = ImageDraw.Draw(strip)

    # Outer edge of left strip = left side; outer edge of right strip = right side.
    if side == "R":
        margin_left  = config.MARGIN_INNER
        margin_right = config.MARGIN_OUTER
    else:
        margin_left  = config.MARGIN_OUTER
        margin_right = config.MARGIN_INNER
    margin_top    = config.MARGIN_TOP
    margin_bottom = config.MARGIN_BOTTOM
    gap           = config.PHOTO_GAP
    footer_height = config.FOOTER_HEIGHT
    photo_border  = config.PHOTO_BORDER

    available_height = (
        config.STRIP_HEIGHT - margin_top - margin_bottom
        - footer_height - (gap * (config.PHOTO_COUNT - 1))
    )
    slot_height_base = available_height // config.PHOTO_COUNT
    slot_height_remainder = available_height % config.PHOTO_COUNT
    slot_width = config.STRIP_WIDTH - margin_left - margin_right

    y = margin_top
    for idx, path in enumerate(photo_paths):
        slot_height = slot_height_base + (1 if idx < slot_height_remainder else 0)

        slot_left = margin_left
        slot_top = y
        slot_right = slot_left + slot_width
        slot_bottom = slot_top + slot_height
        draw.rectangle([slot_left, slot_top, slot_right, slot_bottom], outline="black", width=photo_border)

        inner_w = max(1, slot_width - (photo_border * 2))
        inner_h = max(1, slot_height - (photo_border * 2))
        slot = _fit_photo_to_slot(path, inner_w, inner_h)
        strip.paste(slot, (slot_left + photo_border, slot_top + photo_border))

        if config.STRIP_LABEL and side:
            _draw_strip_label(draw, side, slot_left + photo_border, slot_top + photo_border)

        y += slot_height + gap

    footer_top = y - gap  # remove the trailing gap added after the last photo
    footer_bottom = config.STRIP_HEIGHT - margin_bottom
    _draw_footer(draw, config, margin_left, footer_top, slot_width, footer_bottom - footer_top)
    return strip


def _draw_strip_label(draw: ImageDraw.ImageDraw, label: str, x: int, y: int) -> None:
    """Draw a small L/R badge in the top-left corner of a photo."""
    font = ImageFont.load_default(size=72)
    tx, ty = x + 8, y + 6
    # Black outline by drawing the letter offset in 4 directions, then white on top
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
        draw.text((tx + dx, ty + dy), label, font=font, fill="black")
    draw.text((tx, ty), label, font=font, fill="white")


def _fit_photo_to_slot(photo_path: str, slot_width: int, slot_height: int) -> Image.Image:
    with Image.open(photo_path) as src:
        src_rgb = src.convert("RGB")
        return ImageOps.fit(src_rgb, (slot_width, slot_height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def _draw_footer(
    draw: ImageDraw.ImageDraw,
    config: AppConfig,
    left: int,
    top: int,
    width: int,
    height: int,
) -> None:
    box_top = top
    box_bottom = top + height
    draw.rectangle([left, box_top, left + width, box_bottom], outline="black", width=2)

    line_1 = config.EVENT_NAME
    line_2 = config.EVENT_DATE or datetime.now().strftime("%Y-%m-%d")

    try:
        font = ImageFont.load_default(size=config.FOOTER_FONT_SIZE)
    except TypeError:
        font = ImageFont.load_default()

    b1 = draw.textbbox((0, 0), line_1, font=font)
    b2 = draw.textbbox((0, 0), line_2, font=font)
    h1 = b1[3] - b1[1]
    h2 = b2[3] - b2[1]
    line_gap = max(4, config.FOOTER_FONT_SIZE // 6)
    total_text_h = h1 + line_gap + h2

    y_start = box_top + (height - total_text_h) // 2 - b1[1]
    center_x = left + width // 2
    draw.text((center_x - (b1[2] - b1[0]) // 2, y_start), line_1, fill="black", font=font)
    draw.text((center_x - (b2[2] - b2[0]) // 2, y_start + h1 + line_gap), line_2, fill="black", font=font)
