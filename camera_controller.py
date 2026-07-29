from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np


class CameraController(ABC):
    """
    Abstract interface for camera backends.

    Concrete implementations (WebcamController, CanonController, …) hide every
    hardware detail behind this interface so the rest of the application is
    independent of the capture method.
    """

    @abstractmethod
    def connect(self) -> None:
        """Open a connection to the camera device and allocate SDK resources."""

    @abstractmethod
    def start_live_view(self) -> None:
        """Begin streaming preview frames from the camera."""

    @abstractmethod
    def stop_live_view(self) -> None:
        """Stop the preview stream (does not close the session)."""

    @abstractmethod
    def read_frame(self) -> np.ndarray:
        """Return the most-recent preview frame as a BGR numpy array."""

    @abstractmethod
    def capture_photo(self, output_path: Path) -> Path:
        """
        Trigger a full-resolution capture, save the image to *output_path*,
        and return the path of the saved file.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Close the camera session and free all SDK / OS resources."""
