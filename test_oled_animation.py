"""Host-side OLED film countdown animation test.

Run this on the host PC while the Pico is connected and running main.py.

Usage:
    python test_oled_animation.py              # 5-second countdown (default)
    python test_oled_animation.py --seconds 3  # custom duration
"""

import argparse
import time
from click_sound import ClickSound
from config import AppConfig
from oled_display import OledDisplay


def main() -> None:
    parser = argparse.ArgumentParser(description="Test OLED film countdown animation")
    parser.add_argument(
        "--seconds", type=int, default=5,
        help="Number of seconds to count down (default: 5)",
    )
    parser.add_argument(
        "--no-click", action="store_true",
        help="Disable the countdown click sound",
    )
    args = parser.parse_args()

    config = AppConfig()
    if config.PICO_PORT is None:
        print("PICO_PORT is not set in config — nothing to do.")
        return

    click_enabled = config.CLICK_SOUND_ENABLED and not args.no_click
    click = ClickSound(config.CLICK_SOUND_PATH, config.CLICK_SOUND_DURATION_MS) if click_enabled else None

    oled = OledDisplay(config.PICO_PORT)
    try:
        print(f"Starting {args.seconds}s film countdown animation test...")
        for remaining in range(args.seconds, 0, -1):
            print(f"  {remaining}...")
            oled.countdown_sync(photo_num=1, total=1, seconds=remaining)
            if click is not None:
                click.play()
        oled.idle()
        print("Animation test complete.")
        if click is not None:
            # let the final click finish playing before anything purges it
            time.sleep(config.CLICK_SOUND_DURATION_MS / 1000 + 0.3)
    finally:
        oled.close()
        if click is not None:
            click.close()


if __name__ == "__main__":
    main()
