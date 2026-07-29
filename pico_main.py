"""
Photobooth Pico firmware — upload to Pico as main.py.

Listens on USB serial for line-based commands from the host:
  IDLE                       -> show idle/ready screen
  COUNTDOWN:<n>:<status>     -> show big countdown number + status line
  DONE                       -> show "Printing..." screen

The SH1106 driver is embedded so no external packages are needed.
"""

import sys
import select
import time
import framebuf
from machine import I2C, Pin

# ---------------------------------------------------------------------------
# SH1106 driver
# ---------------------------------------------------------------------------

class SH1106(framebuf.FrameBuffer):
    def __init__(self, width, height, i2c, addr=0x3C):
        self.i2c = i2c
        self.addr = addr
        self.width = width
        self.height = height
        self.pages = height // 8
        self.buffer = bytearray(self.pages * width)
        super().__init__(self.buffer, width, height, framebuf.MONO_VLSB)
        self._init()

    def _cmd(self, *cmds):
        buf = bytearray(len(cmds) + 1)
        buf[0] = 0x00
        for i, c in enumerate(cmds):
            buf[i + 1] = c
        self.i2c.writeto(self.addr, buf)

    def _init(self):
        self._cmd(
            0xAE,        # display off
            0xA8, 0x3F,  # mux ratio
            0xD3, 0x00,  # display offset
            0x40,        # start line
            0xA1,        # segment remap
            0xC8,        # COM scan direction
            0xDA, 0x12,  # COM pins
            0x81, 0xFF,  # contrast
            0xA4,        # RAM content
            0xA6,        # normal (not inverted)
            0xD5, 0x80,  # clock div
            0x8D, 0x14,  # charge pump on
            0xAF,        # display on
        )
        self.fill(0)
        self.show()

    def show(self):
        col_offset = 2
        for page in range(self.pages):
            self._cmd(
                0xB0 | page,
                0x00 | (col_offset & 0x0F),
                0x10 | (col_offset >> 4),
            )
            data = bytearray(self.width + 1)
            data[0] = 0x40
            data[1:] = self.buffer[page * self.width:(page + 1) * self.width]
            self.i2c.writeto(self.addr, data)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _draw_big_char(oled, char, x, y, scale=4):
    """Render a single character scaled up using framebuf pixel data."""
    buf = bytearray(8)
    fb = framebuf.FrameBuffer(buf, 8, 8, framebuf.MONO_VLSB)
    fb.fill(0)
    fb.text(char, 0, 0, 1)
    for cy in range(8):
        for cx in range(8):
            # MONO_VLSB: byte index = cx, bit = cy
            if (buf[cx] >> cy) & 1:
                oled.fill_rect(x + cx * scale, y + cy * scale, scale, scale, 1)


def show_error(oled, msg: str):
    oled.fill(0)
    oled.text("! ERROR !", 19, 0, 1)
    oled.text(msg[:16], 0, 20, 1)
    if len(msg) > 16:
        oled.text(msg[16:32], 0, 30, 1)
    oled.show()


def show_idle(oled):
    oled.fill(0)
    oled.text("Photobooth", 19, 20)
    oled.text("Press start!", 16, 36)
    oled.show()


def show_countdown(oled, n: int, status: str):
    oled.fill(0)
    # Status line at top (truncate to 16 chars for 128px)
    oled.text(status[:16], 0, 0, 1)
    # Big number centred below
    s = str(n)
    scale = 4
    char_w = 8 * scale
    total_w = len(s) * char_w
    x = (128 - total_w) // 2
    y = 16
    for i, ch in enumerate(s):
        _draw_big_char(oled, ch, x + i * char_w, y, scale=scale)
    oled.show()


def show_done(oled):
    oled.fill(0)
    oled.text("All done!", 24, 20)
    oled.text("Printing...", 20, 36)
    oled.show()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

# Button flag set by IRQ so the main loop can never miss a press.
_button_flag = False

def _button_irq(pin):
    global _button_flag
    _button_flag = True


def _handle_command(oled, cmd: str) -> None:
    if cmd == "CLEAR":
        oled.fill(0)
        oled.show()
    elif cmd == "IDLE":
        show_idle(oled)
    elif cmd == "DONE":
        show_done(oled)
    elif cmd.startswith("ERROR:"):
        show_error(oled, cmd[6:])
    elif cmd.startswith("COUNTDOWN:"):
        parts = cmd.split(":", 2)
        try:
            n = int(parts[1])
        except (IndexError, ValueError):
            return
        status = parts[2] if len(parts) > 2 else ""
        show_countdown(oled, n, status)


def main():
    global _button_flag

    i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=400_000)
    oled = SH1106(128, 64, i2c)
    show_idle(oled)

    # IRQ-driven button — fires on falling edge (press), never misses events.
    button = Pin(15, Pin.IN, Pin.PULL_UP)
    button.irq(trigger=Pin.IRQ_FALLING, handler=_button_irq)

    # Non-blocking serial: accumulate chars, act on complete lines.
    poll_obj = select.poll()
    poll_obj.register(sys.stdin, select.POLLIN)
    serial_buf = ""

    while True:
        # Button: IRQ sets flag; send to host and debounce here.
        if _button_flag:
            _button_flag = False
            print("BUTTON_PRESS")
            time.sleep_ms(200)  # debounce

        # Serial: drain available bytes without ever blocking on readline.
        if poll_obj.poll(0):  # 0 ms = non-blocking
            ch = sys.stdin.read(1)
            if ch == "\n":
                cmd = serial_buf.strip()
                serial_buf = ""
                if cmd:
                    _handle_command(oled, cmd)
            else:
                serial_buf += ch

        time.sleep_ms(5)  # ~200 Hz loop


main()
