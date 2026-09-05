from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from camera_controller import CameraController
from config import AppConfig

if TYPE_CHECKING:
    from oled_display import OledDisplay

PreviewCallback = Callable[[str, int], None]


class PhotoSession:
    def __init__(
        self,
        camera: CameraController,
        config: AppConfig,
        preview_callback: PreviewCallback | None = None,
        oled: OledDisplay | None = None,
    ):
        self.camera = camera
        self.config = config
        self.preview_callback = preview_callback
        self.oled = oled

    def run(self) -> list[str]:
        session_dir = self._create_session_dir()
        captured: list[str] = []

        for i in range(self.config.PHOTO_COUNT):
            self._run_countdown(i)
            time.sleep(self.config.CAPTURE_SETTLE_SECONDS)

            photo_path = self._build_filename(session_dir, prefix=f"photo_{i + 1}")
            saved_path = self.camera.capture_photo(photo_path)
            captured.append(str(saved_path))

            if i < self.config.PHOTO_COUNT - 1:
                time.sleep(self.config.DELAY_BETWEEN_PHOTOS)

        return captured

    def _run_countdown(self, index: int) -> None:
        for remaining in range(self.config.COUNTDOWN_SECONDS, 0, -1):
            deadline = time.monotonic() + 1.0
            status = f"Photo {index + 1} of {self.config.PHOTO_COUNT}"
            if self.preview_callback is not None:
                self.preview_callback(status, remaining)
            if self.oled is not None:
                self.oled.countdown(index + 1, self.config.PHOTO_COUNT, remaining)
            # Spin for ~1 second calling preview_callback at display rate so
            # the OpenCV window stays responsive (cv2.waitKey pumps Win32 msgs).
            while time.monotonic() < deadline:
                if self.preview_callback is not None:
                    self.preview_callback(status, remaining)
                else:
                    time.sleep(0.05)

    def _build_filename(self, directory: Path, prefix: str = "photo") -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return directory / f"{prefix}_{ts}.jpg"

    def _create_session_dir(self) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.config.CAPTURES_DIR / f"session_{ts}"
        path.mkdir(parents=True, exist_ok=True)
        return path
