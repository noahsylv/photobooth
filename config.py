from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    CAMERA_INDEX: int = 0
    PRINTER_NAME: str = "DS-RX1"
    PRINTER_ROTATION_DEGREES: int = 90

    PHOTO_COUNT: int = 4
    COUNTDOWN_SECONDS: int = 1
    DELAY_BETWEEN_PHOTOS: float = 1.0

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
    STRIP_LABEL: bool = True  # draw 'L'/'R' badge on each photo corner

    CAPTURES_DIR: Path = Path("captures")
    OUTPUT_DIR: Path = Path("output")

    @property
    def STRIP_WIDTH(self) -> int:
        """Derived: strips are adjacent at the cut line, so each is half the print width."""
        return self.PRINT_WIDTH // 2
