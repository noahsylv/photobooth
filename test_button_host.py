"""Host-side button test.

Polls the Pico over serial and prints whenever a button press is reported.
Run this on the host PC while the Pico is connected and running main.py
(close Thonny/any other serial connection first — only one process can
hold the COM port open at a time).

Usage:
    python test_button_host.py
"""

import time

from config import AppConfig
from oled_display import OledDisplay


def main() -> None:
    config = AppConfig()
    if config.PICO_PORT is None:
        print("PICO_PORT is not set in config — nothing to do.")
        return

    oled = OledDisplay(config.PICO_PORT)
    oled.idle()
    print("Waiting for button presses (Ctrl-C to quit)...")
    try:
        while True:
            if oled.check_button():
                print("BUTTON_PRESS received")
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        oled.close()


if __name__ == "__main__":
    main()
