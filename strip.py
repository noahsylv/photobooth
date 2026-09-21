from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps
import numpy as np

from config import AppConfig
from photo_filters import apply_photo_filter


def create_strip(
    photo_paths: list[str],
    output_path: str,
    config: AppConfig,
    single_strip: bool = False,
) -> str:
    if len(photo_paths) != config.PHOTO_COUNT:
        raise ValueError(f"Expected {config.PHOTO_COUNT} photos, got {len(photo_paths)}.")

    left_strip = _build_single_strip(photo_paths, config, "L")

    final_img = Image.new("RGB", (config.PRINT_WIDTH, config.PRINT_HEIGHT), config.STRIP_BACKGROUND_COLOR)
    final_img.paste(left_strip, (0, 0))
    if not single_strip:
        right_strip = _build_single_strip(photo_paths, config, "R")
        # Place the second strip flush against the right edge so the gap between
        # the two strips lands exactly on the 2-inch cut line.
        final_img.paste(right_strip, (config.PRINT_WIDTH - config.STRIP_WIDTH, 0))

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    final_img.save(out_path, quality=95)
    return str(out_path)


def slot_inner_size(config: AppConfig, side: str = "L", idx: int = 0) -> tuple[int, int]:
    """Return the (inner_w, inner_h) a photo is fit into for a given strip slot,
    i.e. the same dimensions _build_single_strip passes to _fit_photo_to_slot."""
    margin_left  = config.MARGIN_INNER if side == "R" else config.MARGIN_OUTER
    margin_right = config.MARGIN_OUTER if side == "R" else config.MARGIN_INNER
    margin_top    = config.MARGIN_TOP
    margin_bottom = config.MARGIN_BOTTOM
    gap           = config.PHOTO_GAP
    footer_height = config.FOOTER_HEIGHT if config.SHOW_FOOTER else 0
    photo_border  = config.PHOTO_BORDER

    available_height = (
        config.STRIP_HEIGHT - margin_top - margin_bottom
        - footer_height - (gap * (config.PHOTO_COUNT - 1))
    )
    slot_height_base = available_height // config.PHOTO_COUNT
    slot_height_remainder = available_height % config.PHOTO_COUNT
    slot_width = config.STRIP_WIDTH - margin_left - margin_right
    slot_height = slot_height_base + (1 if idx < slot_height_remainder else 0)
    return (
        max(1, slot_width - (photo_border * 2)),
        max(1, slot_height - (photo_border * 2)),
    )


def _build_single_strip(photo_paths: list[str], config: AppConfig, side: str = "") -> Image.Image:
    strip = Image.new("RGB", (config.STRIP_WIDTH, config.STRIP_HEIGHT), config.STRIP_BACKGROUND_COLOR)
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
    footer_height = config.FOOTER_HEIGHT if config.SHOW_FOOTER else 0
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
        slot = _fit_photo_to_slot(
            path,
            inner_w,
            inner_h,
            config.PHOTO_FILTER,
            config.PHOTO_FILTER_FINAL_EXPOSURE,
            (config.PHOTO_CROP_CENTER_X, config.PHOTO_CROP_CENTER_Y),
            config.PHOTO_CROP_TOP_TRIM,
            config.PHOTO_CROP_BOTTOM_TRIM,
        )
        strip.paste(slot, (slot_left + photo_border, slot_top + photo_border))

        if config.STRIP_LABEL and side:
            _draw_strip_label(draw, side, slot_left + photo_border, slot_top + photo_border)

        y += slot_height + gap

    footer_top = y - gap  # remove the trailing gap added after the last photo
    footer_bottom = config.STRIP_HEIGHT - margin_bottom
    if config.SHOW_FOOTER:
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


def _apply_filter(img: Image.Image, filter_name: str, final_exposure: float = 1.0) -> Image.Image:
    if filter_name == "final":
        return apply_photo_filter(img, filter_name, exposure_factor=final_exposure)
    if filter_name == "bw":
        return ImageOps.grayscale(img).convert("RGB")
    if filter_name == "vintage":
        grey = ImageOps.grayscale(img)
        grey = ImageEnhance.Contrast(grey).enhance(1.4)
        grey = ImageEnhance.Brightness(grey).enhance(1.1)
        arr = np.array(grey, dtype=float)
        grain = np.random.normal(0, 8, arr.shape)
        arr = np.clip(arr + grain, 0, 255).astype(np.uint8)
        return Image.fromarray(arr).convert("RGB")
    if filter_name == "vintage2":
        arr = np.array(img, dtype=float) / 255.0  # H x W x 3, range [0, 1]

        # Crush shadows: power > 1 compresses shadow detail toward black
        arr = np.power(np.clip(arr, 0, 1), 1.25)
        # Raise black point + bring highlights down: remap [0,1] → [0.06, 0.88]
        arr = arr * (0.88 - 0.06) + 0.06

        # Luminance for shadow/highlight masking
        lum = (0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2])[:, :, np.newaxis]
        shadow_w    = np.clip(1.0 - lum / 0.35, 0, 1)      # strongest in dark areas
        highlight_w = np.clip((lum - 0.65) / 0.35, 0, 1)   # strongest in bright areas

        # Shadow cast: blue + magenta → boost R and B, pull G down
        arr += shadow_w    * np.array([ 0.03, -0.05,  0.07])
        # Highlight cast: yellow + magenta → boost R, slight G, reduce B
        arr += highlight_w * np.array([ 0.05,  0.02, -0.03])

        return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))
    if filter_name == "sepia":
        grey = ImageOps.grayscale(img)
        sepia = Image.new("RGB", grey.size)
        pixels = grey.load()
        out = sepia.load()
        for y in range(grey.height):
            for x in range(grey.width):
                v = pixels[x, y]
                out[x, y] = (
                    min(255, int(v * 1.08)),
                    min(255, int(v * 0.86)),
                    min(255, int(v * 0.67)),
                )
        return sepia
    return img  # "none" or unknown


def _fit_photo_to_slot(
    photo_path: str,
    slot_width: int,
    slot_height: int,
    photo_filter: str = "none",
    final_exposure: float = 1.0,
    crop_center: tuple[float, float] = (0.5, 0.5),
    top_trim: float = 0.0,
    bottom_trim: float = 0.0,
) -> Image.Image:
    with Image.open(photo_path) as src:
        src = ImageOps.exif_transpose(src)
        src_rgb = src.convert("RGB")
        src_rgb = _trim_top_bottom(src_rgb, top_trim, bottom_trim)
        fitted = _cover_crop(src_rgb, slot_width, slot_height, crop_center)
        return _apply_filter(fitted, photo_filter, final_exposure)


def _trim_top_bottom(img: Image.Image, top_trim: float, bottom_trim: float) -> Image.Image:
    """Remove a fixed fraction of the image's height from the top and/or bottom."""
    if top_trim <= 0 and bottom_trim <= 0:
        return img
    w, h = img.size
    top = min(h - 1, max(0, int(h * top_trim)))
    bottom = h - min(h - top - 1, max(0, int(h * bottom_trim)))
    return img.crop((0, top, w, bottom))


# Zoom-in factor (fraction of the max-cover crop) used at the extremes of
# PHOTO_CROP_CENTER_Y/X (0 or 1). Purely internal: it exists only to give
# the centering room to shift the frame up/down. The actual zoom applied is
# scaled by how far the center is from 0.5, so center=0.5 always yields the
# original, undistorted, un-zoomed crop (matching pre-recentering behavior)
# and moving away from 0.5 progressively zooms in just enough to allow it.
_MIN_CROP_ZOOM = 0.65


def _cover_crop(
    img: Image.Image,
    target_w: int,
    target_h: int,
    center: tuple[float, float] = (0.5, 0.5),
) -> Image.Image:
    """Crop *img* to a target_w/target_h box and resize to that exact size.

    Unlike ImageOps.fit, the crop box is shrunk on both axes (not just the
    one axis that naturally overflows) whenever *center* moves away from
    (0.5, 0.5), so there is slack on both axes for *center* to shift the crop
    around in — otherwise the axis matching the source's aspect ratio has
    zero slack and its centering value is a no-op. At exactly (0.5, 0.5) no
    extra zoom is applied, reproducing the original undistorted crop. The
    output aspect ratio always matches target_w/target_h, so the image is
    never stretched.
    """
    box = cover_crop_box(img, target_w, target_h, center)
    return img.resize((target_w, target_h), resample=Image.Resampling.LANCZOS, box=box)


def cover_crop_box(
    img: Image.Image,
    target_w: int,
    target_h: int,
    center: tuple[float, float] = (0.5, 0.5),
) -> tuple[float, float, float, float]:
    """Return the (x0, y0, x1, y1) crop box _cover_crop would use, without resizing."""
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        crop_h = src_h
        crop_w = crop_h * target_ratio
    else:
        crop_w = src_w
        crop_h = crop_w / target_ratio

    cx = min(1.0, max(0.0, center[0]))
    cy = min(1.0, max(0.0, center[1]))
    # How far the requested center is from dead-center, 0 (centered) .. 1 (extreme).
    offset = max(abs(cx - 0.5), abs(cy - 0.5)) * 2
    zoom = 1.0 - offset * (1.0 - _MIN_CROP_ZOOM)
    crop_w *= zoom
    crop_h *= zoom

    x = (src_w - crop_w) * cx
    y = (src_h - crop_h) * cy
    return (x, y, x + crop_w, y + crop_h)



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
