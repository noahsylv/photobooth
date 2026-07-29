from __future__ import annotations

import argparse
import time
from datetime import datetime

import numpy as np
import cv2

from camera_controller import CameraController
from config import AppConfig
from oled_display import OledDisplay
from printer import check_printer_ready, print_image
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


def run_session(camera: CameraController, config: AppConfig, oled: OledDisplay | None) -> tuple[list[str], str]:
    def preview_callback(status: str, remaining: int) -> None:
        frame = camera.read_frame()
        lines = [status, f"Capturing in {remaining}"]
        preview = draw_overlay(frame, lines)
        cv2.imshow(WINDOW_NAME, preview)
        cv2.waitKey(1)

    session = PhotoSession(camera=camera, config=config, preview_callback=preview_callback, oled=oled)
    photo_paths = session.run()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = config.OUTPUT_DIR / f"print_{ts}.jpg"
    final_print_path = create_strip(photo_paths, str(out_path), config)

    return photo_paths, final_print_path


def run_dry_session(config: AppConfig, oled: OledDisplay | None) -> None:
    """Simulate a full session with sleeps only — no camera, no printer."""
    print("[dry-run] Starting session...")
    for i in range(config.PHOTO_COUNT):
        for remaining in range(config.COUNTDOWN_SECONDS, 0, -1):
            print(f"[dry-run] Photo {i + 1}/{config.PHOTO_COUNT} — {remaining}s")
            if oled is not None:
                oled.countdown(i + 1, config.PHOTO_COUNT, remaining)
            time.sleep(1)
        print(f"[dry-run] *click* photo {i + 1}")
        if i < config.PHOTO_COUNT - 1:
            time.sleep(config.DELAY_BETWEEN_PHOTOS)
    print("[dry-run] Session done, simulating print...")
    if oled is not None:
        oled.done()
    time.sleep(2)
    print("[dry-run] Print complete.")
    if oled is not None:
        oled.idle()


def main() -> None:
    parser = argparse.ArgumentParser(description="Photobooth")
    parser.add_argument("--dry-run", action="store_true", help="Skip camera and printer; test OLED only")
    parser.add_argument("--no-print", action="store_true", help="Run full session and build strip but skip printing")
    parser.add_argument(
        "--camera",
        choices=["canon", "webcam"],
        default=None,
        help="Camera backend to use (default: value of config.CAMERA_BACKEND)",
    )
    args = parser.parse_args()

    config = AppConfig()
    config.CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    oled: OledDisplay | None = None
    if config.PICO_PORT is not None:
        oled = OledDisplay(config.PICO_PORT)

    if args.dry_run:
        import msvcrt
        print("[dry-run] Press ENTER or the start button to trigger a session, or Ctrl-C to quit.")
        if oled is not None:
            oled.idle()
        try:
            while True:
                if oled is not None and oled.check_button():
                    run_dry_session(config, oled)
                elif msvcrt.kbhit():
                    ch = msvcrt.getch()
                    if ch in (b'\r', b'\n'):
                        run_dry_session(config, oled)
                    elif ch.lower() == b'q':
                        break
                else:
                    time.sleep(0.05)
        except KeyboardInterrupt:
            pass
        finally:
            if oled is not None:
                oled.clear()
                oled.close()
        return

    camera = _build_camera(args, config)

    try:
        camera.connect()
        camera.start_live_view()
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        if oled is not None:
            oled.idle()

        camera_ok = True
        _camera_fail_since: float | None = None
        printer_error: str | None = None
        _last_hw_check = 0.0
        _oled_error_active = False
        _CAMERA_GRACE = 5.0  # seconds before a camera failure is treated as an error

        while True:
            try:
                frame = camera.read_frame()
                camera_ok = True
                _camera_fail_since = None
            except RuntimeError:
                frame = None
                if _camera_fail_since is None:
                    _camera_fail_since = time.time()
                camera_ok = (time.time() - _camera_fail_since) < _CAMERA_GRACE

            # Periodic hardware check every 3 s
            now = time.time()
            if now - _last_hw_check > 3.0:
                _last_hw_check = now
                if not args.no_print:
                    printer_error = check_printer_ready(config.PRINTER_NAME)
                else:
                    printer_error = None

            hw_errors: list[str] = []
            if printer_error:
                hw_errors.append(printer_error)
            if not camera_ok:
                hw_errors.append("Camera not ready")

            if hw_errors:
                if frame is None:
                    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
                cv2.imshow(WINDOW_NAME, draw_overlay(frame, ["! HARDWARE ERROR !"] + hw_errors))
                if oled is not None and not _oled_error_active:
                    oled.error(hw_errors[0])
                    _oled_error_active = True
                if cv2.waitKey(200) & 0xFF == ord("q"):
                    break
                continue

            if _oled_error_active:
                if oled is not None:
                    oled.idle()
                _oled_error_active = False

            preview = draw_overlay(frame, ["Press SPACE to start", "Press Q to quit"])
            cv2.imshow(WINDOW_NAME, preview)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

            button_pressed = (oled is not None and oled.check_button())
            if key == ord(" ") or button_pressed:
                try:
                    frame = camera.read_frame()
                    cv2.imshow(WINDOW_NAME, draw_overlay(frame, ["Session running...", "Please look at camera"]))
                    cv2.waitKey(1)
                    photo_paths, final_print_path = run_session(camera, config, oled)
                    if oled is not None:
                        oled.done()

                    if args.no_print:
                        print(f"[no-print] Strip saved to {final_print_path} — printing skipped.")
                        frame = camera.read_frame()
                        cv2.imshow(WINDOW_NAME, draw_overlay(frame, ["Done! (no print)", "Press SPACE for next session"]))
                    else:
                        frame = camera.read_frame()
                        cv2.imshow(WINDOW_NAME, draw_overlay(frame, ["Printing...", "Please wait"]))
                        cv2.waitKey(1)

                        print_image(
                            final_print_path,
                            printer_name=config.PRINTER_NAME,
                            rotation_degrees=config.PRINTER_ROTATION_DEGREES,
                        )

                        frame = camera.read_frame()
                        cv2.imshow(WINDOW_NAME, draw_overlay(frame, ["Done!", "Press SPACE for next session"]))
                    cv2.waitKey(1200)
                    if oled is not None:
                        oled.flush_input()
                        oled.idle()
                except Exception as exc:
                    try:
                        frame = camera.read_frame()
                    except RuntimeError:
                        frame = None
                    if frame is not None:
                        cv2.imshow(WINDOW_NAME, draw_overlay(frame, ["Error", str(exc)[:60]]))
                    cv2.waitKey(1800)
                    if oled is not None:
                        oled.flush_input()
                        oled.idle()
    finally:
        camera.stop_live_view()
        camera.disconnect()
        cv2.destroyAllWindows()
        if oled is not None:
            oled.clear()
            oled.close()


def _build_camera(args: argparse.Namespace, config: AppConfig) -> CameraController:
    """Instantiate the camera backend selected by --camera or config.CAMERA_BACKEND."""
    backend = args.camera if args.camera else config.CAMERA_BACKEND

    if backend == "webcam":
        from webcam_controller import WebcamController
        return WebcamController(index=config.CAMERA_INDEX)

    # Default: Canon EDSDK
    from canon_controller import CanonController
    return CanonController(dll_path=config.EDSDK_DLL_PATH)


if __name__ == "__main__":
    main()
