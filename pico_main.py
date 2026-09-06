"""
Photobooth Pico firmware — upload to Pico as main.py.

Listens on USB serial for line-based commands from the host:
  IDLE                       -> show idle/ready screen
  COUNTDOWN:<n>:<status>     -> show big countdown number + status line
  DONE                       -> show "Printing..." screen
  ANIMATE:<frames>:<delay_ms> -> show a built-in animation sequence

The SH1106 driver is embedded so no external packages are needed.
"""

import sys
import select
import time
import math
import random
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


def _draw_circle(oled, cx, cy, r, col=1):
    """Draw a circle outline using the midpoint algorithm."""
    x, y, d = r, 0, 1 - r
    while x >= y:
        for dx, dy in ((x,y),(x,-y),(-x,y),(-x,-y),(y,x),(y,-x),(-y,x),(-y,-x)):
            px, py = cx + dx, cy + dy
            if 0 <= px < 128 and 0 <= py < 64:
                oled.pixel(px, py, col)
        y += 1
        if d <= 0:
            d += 2 * y + 1
        else:
            x -= 1
            d += 2 * (y - x) + 1


def _draw_line(oled, x0, y0, x1, y1, col=1):
    """Draw a line using Bresenham's algorithm."""
    dx = abs(x1 - x0); dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        if 0 <= x0 < 128 and 0 <= y0 < 64:
            oled.pixel(x0, y0, col)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy; x0 += sx
        if e2 < dx:
            err += dx; y0 += sy


def _fill_pie(oled, cx, cy, r, start_angle, sweep_angle, col=1, step=0.05):
    """Fill a circular pie sector by casting closely-spaced radius lines.

    Faster on MicroPython than a per-pixel angle test since it avoids an
    atan2() call for every pixel in the bounding box.
    """
    a = 0.0
    while a < sweep_angle:
        ang = start_angle + a
        ex = int(cx + r * math.cos(ang))
        ey = int(cy + r * math.sin(ang))
        _draw_line(oled, cx, cy, ex, ey, col)
        a += step
    # Always draw the exact boundary ray so the edge is crisp.
    ang = start_angle + sweep_angle
    ex = int(cx + r * math.cos(ang))
    ey = int(cy + r * math.sin(ang))
    _draw_line(oled, cx, cy, ex, ey, col)


def _draw_text_centered(oled, text: str, y: int, col: int = 1, max_chars: int = 16):
    """Draw 8x8 framebuf text centered on the 128px-wide OLED."""
    clipped = text[:max_chars]
    x = max((128 - len(clipped) * 8) // 2, 0)
    oled.text(clipped, x, y, col)


def show_error(oled, msg: str):
    oled.fill(0)
    _draw_text_centered(oled, "! ERROR !", 0, 1)
    _draw_text_centered(oled, msg, 20, 1)
    if len(msg) > 16:
        _draw_text_centered(oled, msg[16:32], 30, 1)
    oled.show()


def show_idle(oled):
    oled.fill(0)
    _draw_text_centered(oled, "Press Start", 28, 1)
    oled.show()


def show_countdown(oled, n: int, status: str):
    """Film-leader style animated countdown. Runs for ~1 second per call.

    The circle starts empty (light) and a wedge sweeps clockwise from the
    top, progressively filling the circle solid by the end of the second.
    """
    CCX, CCY, R = 64, 28, 22  # circle centre and radius
    FPS = 6
    start_angle = -math.pi / 2  # 12 o'clock
    start_ms = time.ticks_ms()

    for f in range(FPS):
        oled.fill(0)

        # Full-screen crosshairs
        oled.hline(0, CCY, 128, 1)
        oled.vline(CCX, 0, 64, 1)

        # Progressively filled wedge: empty at f=0, full circle at f=FPS-1
        progress = f / (FPS - 1)
        sweep_angle = progress * 2 * math.pi
        if sweep_angle > 0:
            _fill_pie(oled, CCX, CCY, R, start_angle, sweep_angle, 1)

        # Outer circle outline (crisp edge even where already filled)
        _draw_circle(oled, CCX, CCY, R, 1)

        # Clear centre box so number sits on a clean background
        hw = 14
        oled.fill_rect(CCX - hw, CCY - hw, hw * 2, hw * 2, 0)

        # Big countdown number centred in the circle (scale 3 = 24x24 px/digit)
        s = str(n)
        scale = 3
        char_w = 8 * scale
        total_w = len(s) * char_w
        tx = CCX - total_w // 2
        ty = CCY - (8 * scale) // 2
        for i, ch in enumerate(s):
            _draw_big_char(oled, ch, tx + i * char_w, ty, scale=scale)

        # Film grain disabled by request.
        # for _ in range(4):
        #     oled.pixel(random.randint(0, 127), random.randint(0, 63), 1)

        oled.show()
        target_ms = time.ticks_add(start_ms, (f + 1) * 1000 // FPS)
        wait_ms = time.ticks_diff(target_ms, time.ticks_ms())
        if wait_ms > 0:
            time.sleep_ms(wait_ms)
    print("COUNTDOWN_DONE")


def show_done(oled):
    oled.fill(0)
    _draw_text_centered(oled, "Printing...", 20, 1)
    _draw_text_centered(oled, "Pickup outside", 36, 1)
    oled.show()

def show_animation(oled, frames: int, delay_ms: int) -> None:
    """Render a simple built-in animation sequence on the OLED."""
    for frame in range(frames):
        oled.fill(0)
        # bouncing square animation
        step = frame % 16
        if step < 8:
            x = 10 + step * 9
        else:
            x = 10 + (15 - step) * 9
        y = 26
        oled.rect(0, 0, 128, 64, 1)
        _draw_text_centered(oled, "OLED ANIM", 4, 1)
        oled.fill_rect(x, y, 10, 10, 1)
        _draw_text_centered(oled, f"Frame {frame + 1}/{frames}", 52, 1)
        oled.show()
        time.sleep_ms(delay_ms)

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
    elif cmd.startswith("ANIMATE:"):
        parts = cmd.split(":", 2)
        try:
            frames = int(parts[1])
            delay_ms = int(parts[2]) if len(parts) > 2 else 100
        except (IndexError, ValueError):
            return
        show_animation(oled, frames, delay_ms)


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
