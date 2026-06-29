from __future__ import annotations

from datetime import datetime

import cv2

from camera import Camera
from config import AppConfig
from printer import print_image
from session import PhotoSession
from strip import create_strip

WINDOW_NAME = "Photobooth"


def draw_overlay(frame, lines: list[str]):
    overlay = frame.copy()
    cv2.rectangle(overlay, (20, 20), (950, 170), (0, 0, 0), -1)
    frame = cv2.addWeighted(overlay, 0.45, frame, 0.55, 0)

    y = 65
    for line in lines:
        cv2.putText(
            frame,
            line,
            (40, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        y += 40

    return frame


def run_session(camera: Camera, config: AppConfig) -> tuple[list[str], str]:
    def preview_callback(status: str, remaining: int) -> None:
        frame = camera.read_frame()
        lines = [status, f"Capturing in {remaining}"]
        preview = draw_overlay(frame, lines)
        cv2.imshow(WINDOW_NAME, preview)
        cv2.waitKey(1)

    session = PhotoSession(camera=camera, config=config, preview_callback=preview_callback)
    photo_paths = session.run()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = config.OUTPUT_DIR / f"print_{ts}.jpg"
    final_print_path = create_strip(photo_paths, str(out_path), config)

    return photo_paths, final_print_path


def main() -> None:
    config = AppConfig()
    config.CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    camera = Camera(index=config.CAMERA_INDEX)

    try:
        camera.start()
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)

        while True:
            frame = camera.read_frame()
            preview = draw_overlay(frame, ["Press SPACE to start", "Press Q to quit"])
            cv2.imshow(WINDOW_NAME, preview)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

            if key == ord(" "):
                try:
                    frame = camera.read_frame()
                    cv2.imshow(WINDOW_NAME, draw_overlay(frame, ["Session running...", "Please look at camera"]))
                    cv2.waitKey(1)

                    _, print_path = run_session(camera, config)

                    frame = camera.read_frame()
                    cv2.imshow(WINDOW_NAME, draw_overlay(frame, ["Printing...", "Please wait"]))
                    cv2.waitKey(1)

                    print_image(
                        print_path,
                        printer_name=config.PRINTER_NAME,
                        rotation_degrees=config.PRINTER_ROTATION_DEGREES,
                    )

                    frame = camera.read_frame()
                    cv2.imshow(WINDOW_NAME, draw_overlay(frame, ["Done!", "Press SPACE for next session"]))
                    cv2.waitKey(1200)
                except Exception as exc:
                    frame = camera.read_frame()
                    cv2.imshow(WINDOW_NAME, draw_overlay(frame, ["Error", str(exc)[:60]]))
                    cv2.waitKey(1800)
    finally:
        camera.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
