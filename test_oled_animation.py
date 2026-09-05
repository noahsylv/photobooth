"""Host-side OLED film countdown animation test.

Run this on the host PC while the Pico is connected and running main.py.

Usage:
    python test_oled_animation.py              # 5-second countdown (default)
    python test_oled_animation.py --seconds 3  # custom duration
"""

import argparse
import time
from config import AppConfig
from oled_display import OledDisplay


def main() -> None:
    parser = argparse.ArgumentParser(description="Test OLED film countdown animation")
    parser.add_argument(
        "--seconds", type=int, default=5,
        help="Number of seconds to count down (default: 5)",
    )
    args = parser.parse_args()

    config = AppConfig()
    if config.PICO_PORT is None:
        print("PICO_PORT is not set in config — nothing to do.")
        return

    oled = OledDisplay(config.PICO_PORT)
    try:
        print(f"Starting {args.seconds}s film countdown animation test...")
        for remaining in range(args.seconds, 0, -1):
            deadline = time.monotonic() + 1.0
            print(f"  {remaining}...")
            oled.countdown(photo_num=1, total=1, seconds=remaining)
            time.sleep(max(0.0, deadline - time.monotonic()))
        oled.idle()
        print("Animation test complete.")
    finally:
        oled.close()


if __name__ == "__main__":
    main()
