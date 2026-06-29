from __future__ import annotations

from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


class Camera:
    def __init__(self, index: int = 0):
        self.index = index
        self._cap: cv2.VideoCapture | None = None
        self._last_frame: np.ndarray | None = None

    def start(self) -> None:
        if self._cap is not None:
            return

        cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open camera index {self.index}.")

        self._cap = cap

    def read_frame(self) -> np.ndarray:
        if self._cap is None:
            raise RuntimeError("Camera is not started.")

        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise RuntimeError("Failed to read frame from camera.")

        self._last_frame = frame
        return frame

    def capture_jpeg(self, output_path: str) -> str:
        if self._last_frame is None:
            self.read_frame()

        if self._last_frame is None:
            raise RuntimeError("No frame available to capture.")

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        success = cv2.imwrite(str(out), self._last_frame)
        if not success:
            raise RuntimeError(f"Failed to save image to {out}.")

        return str(out)

    def build_capture_filename(self, directory: Path, prefix: str = "photo") -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return directory / f"{prefix}_{ts}.jpg"

    def stop(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            self._last_frame = None
