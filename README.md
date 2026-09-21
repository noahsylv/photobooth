# Scripts Reference

CLI-runnable scripts in this repo and their arguments. Run with `python <script>.py [args]` (or `py` on Windows) from the project root with the venv activated.

## `app.py`
Main photobooth runtime: countdown, capture, build strip, print.

| Arg | Description |
| --- | --- |
| `--dry-run` | Skip camera and printer; test OLED only |
| `--no-print` | Run full session and build strip but skip printing |
| `--preview` | Show the live camera preview window |
| `--camera {canon,webcam}` | Camera backend to use (default: `config.CAMERA_BACKEND`) |

## `reprint_session.py`
Rebuild (and optionally print) a strip from an existing capture session or an arbitrary folder of photos.

| Arg | Description |
| --- | --- |
| `--filter {none,bw,sepia,vintage,vintage2,final}` | Filter to apply; defaults to `config.PHOTO_FILTER` |
| `--session-dir PATH` | Session directory to use; defaults to the newest session |
| `--back N` | Select the Nth most recent session: `0`=most recent (default), `1`=2nd most recent, `2`=3rd most recent, etc. |
| `--photos-dir PATH` | Arbitrary folder of photos (JPG/PNG) to use instead of a capture session (overrides `--session-dir`/`--captures-dir`) |
| `--indices 0,2,3,7` | Pick which photos to use when the folder has more than `PHOTO_COUNT` images; indices follow alphabetical filename order |
| `--captures-dir PATH` | Directory containing sessions; defaults to `config.py` |
| `--output PATH`, `-o PATH` | Output strip path; defaults to `output/reprint_<timestamp>.jpg` |
| `--final-exposure FLOAT` | Exposure multiplier for the `final` filter |
| `--no-crop` | Keep each photo's full frame, fitting it inside the slot with padding |
| `--single-strip` | Render only the left strip and leave the other half of the print blank |
| `--show` | Open a preview window of the rebuilt strip before printing |
| `--print` | Send the rebuilt strip to the configured printer |
| `--no-print` | Only rebuild the strip; do not print it (default) |

## `crop_preview.py`
Shows the full, uncropped photo with a box around the region the current crop config (`PHOTO_CROP_CENTER_X/Y`, `PHOTO_CROP_TOP_TRIM`/`BOTTOM_TRIM`) would keep for the strip.

| Arg | Description |
| --- | --- |
| `--photo PATH` | Exact photo path to preview; defaults to the most recent captured photo |
| `--back N` | Select the Nth most recent captured photo instead of the latest: `0`=most recent (default), `1`=2nd most recent, etc. |
| `--captures-dir PATH` | Directory containing sessions; defaults to `config.py` |
| `--side {L,R}` | Which strip side's slot aspect ratio to preview (default: `L`) |

## `apply_filter.py`
Apply a named photo filter to the most recent photo from the latest session and display the before/after.

| Arg | Description |
| --- | --- |
| `filter {none,bw,sepia,vintage,vintage2,final}` | (positional, required) Filter to apply |
| `--output PATH`, `-o PATH` | Output path for the filtered image (default: `output/filtered_latest.jpg`) |
| `--captures-dir PATH` | Directory containing capture sessions (default: `captures`) |
| `--final-exposure FLOAT` | Exposure multiplier for the `final` filter; overrides config value |
| `--no-display` | Save the filtered image without opening a display window |

## `test_oled_animation.py`
Host-side test of the OLED film countdown animation (Pico must be connected and running `pico_main.py`).

| Arg | Description |
| --- | --- |
| `--seconds INT` | Number of seconds to count down (default: 5) |
| `--no-click` | Disable the countdown click sound |

## `display_latest_photo.py`
Shows the latest captured photo from the most recent session. No CLI args.

## `preview.py`
Live strip layout preview with adjustable trackbars (spacing, margins, etc.) using the most recent capture session. No CLI args. Keys: `Q`/`Esc` to quit, `R` to reload photos.

## `clear_oled.py`
Clears the OLED display; run manually when the screen is stuck. No CLI args.

## `camera_test.py`
Quick webcam smoke test — press SPACE to save a photo, Q to quit. No CLI args.

## `test_canon.py`
Currently empty (placeholder for Canon camera testing).

---

### Pico-side scripts (upload to the Pico, not run on the host)
- `pico_main.py` — OLED firmware listening for `IDLE` / `COUNTDOWN:<n>:<status>` / `DONE` / `ANIMATE:<frames>:<delay_ms>` commands over USB serial.
- `test_components.py` — embedded SSD1306 driver test.
- `test_button.py` — simple button-press test.
