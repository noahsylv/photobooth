from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from camera_controller import CameraController


class WebcamController(CameraController):
    """
    Camera backend that streams from a UVC / DirectShow webcam via OpenCV.

    This was the original capture method.  It does *not* support the camera's
    built-in flash because the camera stays in video-streaming mode.  Use
    CanonController for flash support and full-resolution JPEG capture.
    """

    def __init__(self, index: int = 0) -> None:
        self._index = index
        self._cap: cv2.VideoCapture | None = None
        self._last_frame: np.ndarray | None = None

    # ── CameraController interface ────────────────────────────────────────────

    def connect(self) -> None:
        if self._cap is not None:
            return
        cap = cv2.VideoCapture(self._index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open webcam at index {self._index}.")
        self._cap = cap

    def start_live_view(self) -> None:
        """No-op: OpenCV starts streaming on the first read_frame() call."""

    def stop_live_view(self) -> None:
        """No-op: streaming is tied to the capture session for webcams."""

    def read_frame(self) -> np.ndarray:
        if self._cap is None:
            raise RuntimeError("Camera is not connected. Call connect() first.")
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise RuntimeError("Failed to read frame from webcam.")
        self._last_frame = frame
        return frame

    def capture_photo(self, output_path: Path) -> Path:
        if self._last_frame is None:
            self.read_frame()
        if self._last_frame is None:
            raise RuntimeError("No frame available to capture.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(output_path), self._last_frame):
            raise RuntimeError(f"Failed to save image to {output_path}.")
        return output_path

    def disconnect(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            self._last_frame = None
