# Photobooth Software Implementation Plan

## Goal

Build a custom Windows-based photobooth application for:

* Beelink Mini PC running Windows
* Canon EOS R50 connected over USB
* DNP DS-RX1HS printer connected over USB
* Standard DNP 4×6 media
* DNP driver configured with `2inch cut: Enable`
* Output: two individual 2×6 photo strips per session

The application should eventually run like an appliance:

1. User presses a key/button to start.
2. App shows countdown.
3. App captures 4 photos.
4. App generates a 4×6 print layout containing two duplicated 2×6 strips.
5. App sends one print job to the DNP printer.
6. Printer cuts the output into two physical 2×6 strips.
7. App returns to idle.

## Important Printer Findings

The DNP DS-RX1HS is using standard 4×6 media.

The driver setting `2inch cut: Enable` is available and confirmed working.

With 2-inch cut enabled, a landscape 6×4 image is split into two physical 2×6 strips:

```text
Input image: 1800 × 1200 px

+----------------------+----------------------+
| Strip Left           | Strip Right          |
|                      |                      |
|                      |                      |
+----------------------+----------------------+

Output:

Strip Left  -> physical 2×6 strip
Strip Right -> physical 2×6 strip
```

Therefore, the software should generate one final print image at:

```text
1800 × 1200 px
300 DPI
landscape
```

Each half is:

```text
900 × 1200 px
```

Each half becomes one physical 2×6 strip after printing and cutting.

## Tech Stack

Use Python on Windows.

Recommended packages:

```text
opencv-python
pillow
pywin32
keyboard
```

Optional later:

```text
PySide6
qrcode
```

Initial development can use OpenCV windows. Later, replace with PySide6 for a polished fullscreen kiosk UI.

## Project Structure

```text
photobooth/
│
├── app.py
├── camera.py
├── session.py
├── strip.py
├── printer.py
├── config.py
│
├── assets/
│   ├── fonts/
│   ├── sounds/
│   └── overlays/
│
├── captures/
├── output/
├── test_assets/
│
├── requirements.txt
├── README.md
└── .gitignore
```

## .gitignore

```gitignore
__pycache__/
*.pyc
.venv/
captures/
output/
*.log
.env
```

## Requirements

```text
opencv-python
pillow
pywin32
keyboard
```

## Milestone 1: Camera Preview and Capture

Implement `camera.py`.

Use OpenCV to read from the Canon R50 in USB video/streaming mode.

Requirements:

* Open camera using `cv2.VideoCapture(0, cv2.CAP_DSHOW)`.
* Provide live frames.
* Save a frame as JPEG.
* Release camera cleanly on exit.

Example API:

```python
class Camera:
    def __init__(self, index: int = 0):
        ...

    def start(self) -> None:
        ...

    def read_frame(self):
        ...

    def capture_jpeg(self, output_path: str) -> str:
        ...

    def stop(self) -> None:
        ...
```

For now, captured photos can be frames from the live camera feed. Later, this can be upgraded to full-resolution Canon tethered capture if desired.

## Milestone 2: Basic Session Flow

Implement `session.py`.

A session should:

1. Wait for start input.
2. Capture 4 photos.
3. Delay between photos.
4. Save each image into `captures/session_<timestamp>/`.
5. Return list of captured image paths.

Configurable values:

```python
PHOTO_COUNT = 4
COUNTDOWN_SECONDS = 3
DELAY_BETWEEN_PHOTOS = 1
```

Example API:

```python
class PhotoSession:
    def __init__(self, camera, config):
        ...

    def run(self) -> list[str]:
        ...
```

## Milestone 3: Strip Generation

Implement `strip.py`.

Input:

* 4 captured image paths

Output:

* One final 1800×1200 print image
* Left half and right half should be identical strips
* Final image should be ready for 6×4 landscape printing with 2-inch cut enabled

Important dimensions:

```python
PRINT_WIDTH = 1800
PRINT_HEIGHT = 1200

STRIP_WIDTH = 900
STRIP_HEIGHT = 1200
```

Layout:

```text
Final print image: 1800×1200

+----------------------+----------------------+
| duplicated strip     | duplicated strip     |
+----------------------+----------------------+
```

Each 900×1200 strip should contain:

* 4 stacked photo slots
* optional footer text
* optional date/event name
* optional border/margins

Initial simple layout:

```text
Strip 900×1200

+------------------+
| Photo 1          |
+------------------+
| Photo 2          |
+------------------+
| Photo 3          |
+------------------+
| Photo 4          |
+------------------+
| Event text/date  |
+------------------+
```

Use Pillow.

Example API:

```python
def create_strip(photo_paths: list[str], output_path: str) -> str:
    ...
```

Implementation details:

* Open each photo with Pillow.
* Crop to fit each slot while preserving aspect ratio.
* Resize/crop using center crop.
* Paste photos into strip canvas.
* Add text/footer.
* Duplicate strip onto left and right halves of final canvas.
* Save final image as JPEG or PNG.

## Milestone 4: Printing

Implement `printer.py`.

Use Windows printing via `pywin32`.

Assume DNP printer is installed as:

```text
DS-RX1
```

The driver should already have:

```text
Paper Size: 6x4
2inch cut: Enable
Overcoat: Glossy
Print Quality: 300 x 300 dpi
```

Initial approach:

* Use Windows default image printing if easiest.
* Or use `win32print` / `win32ui` to send the image to the selected printer.

Example API:

```python
def print_image(image_path: str, printer_name: str = "DS-RX1") -> None:
    ...
```

Requirements:

* Print final 1800×1200 image at full page size.
* No scaling margins.
* No unexpected rotation.
* Use landscape 6×4 output.

Testing steps:

1. Print a generated test image.
2. Confirm it outputs two separate 2×6 strips.
3. Confirm left and right strips are identical.
4. Confirm orientation is correct when held vertically.

## Milestone 5: Main App

Implement `app.py`.

Initial CLI/OpenCV version:

* Show live preview.
* Press space to start session.
* Show countdown using OpenCV overlay text.
* Capture 4 photos.
* Generate strip.
* Print strip.
* Return to idle.
* Press Q or Ctrl+C to quit.

Flow:

```text
STARTUP
  ↓
Open camera
  ↓
Idle preview: "Press SPACE to start"
  ↓
Countdown 3, 2, 1
  ↓
Capture photo 1
  ↓
Countdown
  ↓
Capture photo 2
  ↓
Countdown
  ↓
Capture photo 3
  ↓
Countdown
  ↓
Capture photo 4
  ↓
Generate strip
  ↓
Print
  ↓
Return to idle
```

## Milestone 6: Button Support

The physical arcade button should eventually connect through a USB encoder and appear as a keyboard key, likely Space or Enter.

For now:

* Space starts session.
* Q quits.

Later:

* USB arcade encoder maps button to Space.
* No code changes needed.

Optional:

* Add debounce so holding button does not start multiple sessions.

## Milestone 7: Fullscreen UI

Replace OpenCV window with PySide6.

Requirements:

* Fullscreen mode
* Live camera preview
* Large countdown
* Clear status messages:

  * Ready
  * Get Ready
  * Photo 1 of 4
  * Printing
  * Done
  * Error
* Hide mouse cursor
* Auto-return to idle

This can come after the camera/printer pipeline works.

## Milestone 8: Configuration

Create `config.py` or `config.json`.

Configurable values:

```python
CAMERA_INDEX = 0
PRINTER_NAME = "DS-RX1"

PHOTO_COUNT = 4
COUNTDOWN_SECONDS = 3
DELAY_BETWEEN_PHOTOS = 1

PRINT_WIDTH = 1800
PRINT_HEIGHT = 1200
STRIP_WIDTH = 900
STRIP_HEIGHT = 1200

EVENT_NAME = "Noah & Claire"
EVENT_DATE = "2026"
COPIES = 2
```

If `COPIES > 2`, print additional jobs:

```python
prints_needed = math.ceil(COPIES / 2)
```

Since each 4×6 print produces two 2×6 strips.

## Milestone 9: Reliability

Add:

* Logging to `photobooth.log`
* Graceful camera shutdown
* Printer error handling
* Disk space check
* Output folder cleanup option
* Retry printing
* Keyboard escape/admin quit command

Expected error states:

* Camera not found
* Printer not found
* Failed to capture frame
* Failed to generate strip
* Failed to print
* Paper/ribbon out

## Milestone 10: Windows Startup

Once stable:

* Create a `.bat` file to launch the app.
* Add it to Windows Startup folder.
* Disable Windows sleep.
* Optionally enable auto-login.
* Optionally run app fullscreen on boot.

Example `run_booth.bat`:

```bat
cd C:\Users\noahs\photobooth
call .venv\Scripts\activate.bat
py app.py
```

## Acceptance Criteria

The first complete version is successful when:

* App starts on Beelink.
* Canon R50 preview appears.
* Spacebar starts session.
* App captures 4 photos.
* App creates a 1800×1200 print image.
* Final image contains two identical strips side by side.
* DNP RX1HS prints the image.
* With 2-inch cut enabled, printer outputs two separate 2×6 strips.
* App returns to idle and can run another session.

## Important Notes

Do not design the final print image as a portrait 2×6 image.

The correct final print file is landscape 6×4:

```text
1800×1200 px
```

with two strips side by side.

The DNP driver and 2-inch cutter split that landscape image into two physical strips.
