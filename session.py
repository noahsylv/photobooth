from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from config import AppConfig

PreviewCallback = Callable[[str, int], None]


class PhotoSession:
    def __init__(
        self,
        camera,
        config: AppConfig,
        preview_callback: PreviewCallback | None = None,
    ):
        self.camera = camera
        self.config = config
        self.preview_callback = preview_callback

    def run(self) -> list[str]:
        session_dir = self._create_session_dir()
        captured: list[str] = []

        for i in range(self.config.PHOTO_COUNT):
            self._run_countdown(i)

            photo_path = self.camera.build_capture_filename(session_dir, prefix=f"photo_{i + 1}")
            saved_path = self.camera.capture_jpeg(str(photo_path))
            captured.append(saved_path)

            if i < self.config.PHOTO_COUNT - 1:
                time.sleep(self.config.DELAY_BETWEEN_PHOTOS)

        return captured

    def _run_countdown(self, index: int) -> None:
        for remaining in range(self.config.COUNTDOWN_SECONDS, 0, -1):
            if self.preview_callback is not None:
                status = f"Photo {index + 1} of {self.config.PHOTO_COUNT}"
                self.preview_callback(status, remaining)
            time.sleep(1)

    def _create_session_dir(self) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.config.CAPTURES_DIR / f"session_{ts}"
        path.mkdir(parents=True, exist_ok=True)
        return path
