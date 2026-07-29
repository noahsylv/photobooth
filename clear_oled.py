"""Clears the OLED display. Run manually when the screen is stuck."""
from config import AppConfig
from oled_display import OledDisplay

config = AppConfig()
if config.PICO_PORT is None:
    print("PICO_PORT is not set in config — nothing to do.")
else:
    oled = OledDisplay(config.PICO_PORT)
    oled.clear()
    oled.close()
    print("OLED cleared.")
