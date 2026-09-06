from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    CAMERA_INDEX: int = 0
    PRINTER_NAME: str = "DS-RX1"
    PRINTER_ROTATION_DEGREES: int = 90

    PHOTO_COUNT: int = 4
    COUNTDOWN_SECONDS: int = 3 # 3
    DELAY_BETWEEN_PHOTOS: float = 1.5
    CAPTURE_SETTLE_SECONDS: float = 0.65

    # Pre-rotation dimensions: 1240×1844 rotated 90° → 1844×1240 matches the
    # printer DC exactly so the image fills the page with no letterboxing.
    PRINT_WIDTH: int = 1240
    PRINT_HEIGHT: int = 1844
    STRIP_HEIGHT: int = 1844

    EVENT_NAME: str = "N+C Wedding"
    EVENT_DATE: str = "2026"

    # NOTE: I think outer should always be 2x inner

    # Strip layout — outer/inner control the horizontal edges; top/bottom are independent.
    MARGIN_OUTER: int = 50    # px on the outer horizontal edge of each strip
    MARGIN_INNER: int = 25    # px on the inner horizontal edge (adjacent to cut line)
    MARGIN_TOP: int = 50      # px on the top edge of each strip
    MARGIN_BOTTOM: int = 50   # px on the bottom edge of each strip
    PHOTO_GAP: int = 8        # px gap between each photo
    FOOTER_HEIGHT: int = 80   # px height of the event text footer
    PHOTO_BORDER: int = 2     # px border drawn around each photo slot
    FOOTER_FONT_SIZE: int = 30  # pt font size for event name / date text
    SHOW_FOOTER: bool = False   # set False to hide the footer and reclaim the space
    STRIP_LABEL: bool = False  # draw 'L'/'R' badge on each photo corner
    STRIP_BACKGROUND_COLOR: str = "black"  # background colour for the strip canvas
    PHOTO_FILTER: str = "final"  # photo filter applied to each image: "none", "bw", "sepia", "vintage", "vintage2", "final"
    # PHOTO_FILTER_FINAL_EXPOSURE: float = 1.40  # exposure factor used by the 'final' filter
    PHOTO_FILTER_FINAL_EXPOSURE: float = .95  # exposure factor used by the 'final' filter

    CAPTURES_DIR: Path = Path("captures")
    OUTPUT_DIR: Path = Path("output")

    # Set to None to disable the Pico OLED (e.g. when Pico is not connected)
    PICO_PORT: str | None = "COM3"

    # Camera backend: "canon" (default, EDSDK tethered) or "webcam" (OpenCV/UVC)
    CAMERA_BACKEND: str = "canon"

    # Full path to EDSDK.dll.  None = auto-detect from common Canon install paths.
    EDSDK_DLL_PATH: str | None = None

    # Countdown tick/click sound (plays every second during the countdown)
    CLICK_SOUND_ENABLED: bool = True
    CLICK_SOUND_PATH: Path = Path("audio/timer.mp3")
    CLICK_SOUND_DURATION_MS: int = 150  # how much of the file's start to play

    @property
    def STRIP_WIDTH(self) -> int:
        """Derived: strips are adjacent at the cut line, so each is half the print width."""
        return self.PRINT_WIDTH // 2
