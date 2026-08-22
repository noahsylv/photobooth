from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

VALID_FILTERS = ("none", "bw", "sepia", "vintage", "vintage2", "final")


def _build_curve_lut(points: list[tuple[int, int]]) -> np.ndarray:
    x, y = zip(*points)
    lut = np.interp(np.arange(256), x, y).astype(np.uint8)
    return lut


def _apply_rgb_tone_curve(image: Image.Image, points: list[tuple[int, int]]) -> Image.Image:
    lut = _build_curve_lut(points)
    r, g, b = image.split()
    return Image.merge("RGB", (r.point(lut), g.point(lut), b.point(lut)))


def _adjust_saturation(image: Image.Image, factor: float) -> Image.Image:
    hsv = image.convert("HSV")
    h, s, v = hsv.split()
    s = s.point(lambda p: int(np.clip(p * factor, 0, 255)))
    return Image.merge("HSV", (h, s, v)).convert("RGB")


def _apply_split_tone(image: Image.Image) -> Image.Image:
    # XMP: shadow hue 36 sat 33, midtone hue 55 sat 27, highlight hue 45 sat 10
    # Use additive shifts rather than blending toward pure hue to avoid colour crushing.
    arr = np.array(image, dtype=float) / 255.0
    lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]

    shadow_mask    = np.clip((0.40 - lum) / 0.40, 0, 1)[:, :, np.newaxis]
    midtone_mask   = (np.clip((lum - 0.15) / 0.35, 0, 1) * np.clip((0.85 - lum) / 0.35, 0, 1))[:, :, np.newaxis]
    highlight_mask = np.clip((lum - 0.60) / 0.40, 0, 1)[:, :, np.newaxis]

    # Warm sepia: +R, -G, -B — reducing G is critical to avoid olive/cool cast
    shadow_shift    = np.array([ 0.06, -0.03, -0.13])
    midtone_shift   = np.array([ 0.06, -0.04, -0.11])
    highlight_shift = np.array([ 0.03, -0.01, -0.06])

    arr = arr + shadow_mask    * shadow_shift
    arr = arr + midtone_mask   * midtone_shift
    arr = arr + highlight_mask * highlight_shift
    return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))


def _apply_grain(image: Image.Image, strength: float = 0.06) -> Image.Image:
    arr = np.array(image, dtype=float)
    noise = np.random.normal(0, strength * 255.0, arr.shape)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def apply_photo_filter(image: Image.Image, filter_name: str, exposure_factor: float = 1.0) -> Image.Image:
    if filter_name == "bw":
        return ImageOps.grayscale(image).convert("RGB")

    if filter_name == "vintage":
        grey = ImageOps.grayscale(image)
        grey = ImageEnhance.Contrast(grey).enhance(1.4)
        grey = ImageEnhance.Brightness(grey).enhance(1.1)
        arr = np.array(grey, dtype=float)
        grain = np.random.normal(0, 8, arr.shape)
        arr = np.clip(arr + grain, 0, 255).astype(np.uint8)
        return Image.fromarray(arr).convert("RGB")

    if filter_name == "vintage2":
        arr = np.array(image, dtype=float) / 255.0
        arr = np.power(np.clip(arr, 0, 1), 1.25)
        arr = arr * (0.88 - 0.06) + 0.06

        lum = (
            0.2126 * arr[:, :, 0]
            + 0.7152 * arr[:, :, 1]
            + 0.0722 * arr[:, :, 2]
        )[:, :, np.newaxis]
        shadow_w = np.clip(1.0 - lum / 0.35, 0, 1)
        highlight_w = np.clip((lum - 0.65) / 0.35, 0, 1)

        arr += shadow_w * np.array([0.03, -0.05, 0.07])
        arr += highlight_w * np.array([0.05, 0.02, -0.03])

        return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))

    if filter_name == "sepia":
        grey = ImageOps.grayscale(image)
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

    if filter_name == "final":
        grey = image.convert("L").convert("RGB")  # grayscale first — no colour bleed into pipeline
        adjusted = ImageEnhance.Brightness(grey).enhance(exposure_factor)
        adjusted = ImageEnhance.Contrast(adjusted).enhance(0.75)
        adjusted = _apply_rgb_tone_curve(
            adjusted,
            [(0, 0), (64, 30), (176, 164), (250, 191), (255, 255)],
        )
        adjusted = _apply_split_tone(adjusted)
        adjusted = _apply_grain(adjusted, strength=0.08)
        return adjusted

    return image


def apply_photo_filter_to_path(
    source_path: Path,
    target_path: Path,
    filter_name: str,
    exposure_factor: float = 1.0,
    quality: int = 95,
) -> Path:
    with Image.open(source_path) as src:
        image = src.convert("RGB")
        filtered = apply_photo_filter(image, filter_name, exposure_factor=exposure_factor)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        filtered.save(target_path, quality=quality)
    return target_path
