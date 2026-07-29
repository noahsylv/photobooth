import time
import framebuf
from micropython import const
from machine import I2C, Pin

# --- Embedded SSD1306 driver (no external module needed) ---
_SET_CONTRAST = const(0x81)
_SET_ENTIRE_ON = const(0xA4)
_SET_NORM_INV = const(0xA6)
_SET_DISP = const(0xAE)
_SET_MEM_ADDR = const(0x20)
_SET_COL_ADDR = const(0x21)
_SET_PAGE_ADDR = const(0x22)
_SET_DISP_START_LINE = const(0x40)
_SET_SEG_REMAP = const(0xA0)
_SET_MUX_RATIO = const(0xA8)
_SET_COM_OUT_DIR = const(0xC0)
_SET_DISP_OFFSET = const(0xD3)
_SET_COM_PIN_CFG = const(0xDA)
_SET_DISP_CLK_DIV = const(0xD5)
_SET_PRECHARGE = const(0xD9)
_SET_VCOM_DESEL = const(0xDB)
_SET_CHARGE_PUMP = const(0x8D)


class SSD1306(framebuf.FrameBuffer):
    def __init__(self, width, height, external_vcc=False):
        self.width = width
        self.height = height
        self.external_vcc = external_vcc
        self.pages = height // 8
        self.buffer = bytearray(self.pages * width)
        super().__init__(self.buffer, width, height, framebuf.MONO_VLSB)
        self._init_display()

    def _init_display(self):
        for cmd in (
            _SET_DISP,
            _SET_MEM_ADDR, 0x00,
            _SET_DISP_START_LINE,
            _SET_SEG_REMAP | 0x01,
            _SET_MUX_RATIO, self.height - 1,
            _SET_COM_OUT_DIR | 0x08,
            _SET_DISP_OFFSET, 0x00,
            _SET_COM_PIN_CFG, 0x02 if self.width > 2 * self.height else 0x12,
            _SET_DISP_CLK_DIV, 0x80,
            _SET_PRECHARGE, 0x22 if self.external_vcc else 0xF1,
            _SET_VCOM_DESEL, 0x30,
            _SET_CONTRAST, 0xFF,
            _SET_ENTIRE_ON,
            _SET_NORM_INV,
            _SET_CHARGE_PUMP, 0x10 if self.external_vcc else 0x14,
            _SET_DISP | 0x01,
        ):
            self._write_cmd(cmd)
        self.fill(0)
        self.show()

    def show(self):
        x0, x1 = 0, self.width - 1
        self._write_cmd(_SET_COL_ADDR); self._write_cmd(x0); self._write_cmd(x1)
        self._write_cmd(_SET_PAGE_ADDR); self._write_cmd(0); self._write_cmd(self.pages - 1)
        self._write_data(self.buffer)


class SSD1306_I2C(SSD1306):
    def __init__(self, width, height, i2c, addr=0x3C, external_vcc=False):
        self.i2c = i2c
        self.addr = addr
        self._tmp = bytearray(2)
        self._data_buf = bytearray(width * (height // 8) + 1)
        self._data_buf[0] = 0x40
        super().__init__(width, height, external_vcc)

    def _write_cmd(self, cmd):
        self._tmp[0] = 0x00  # Co=0, D/C#=0 — command stream
        self._tmp[1] = cmd
        self.i2c.writeto(self.addr, self._tmp)

    def _write_data(self, buf):
        # Prepend 0x40 data-mode byte and send as a single writeto
        self._data_buf[1:] = buf
        self.i2c.writeto(self.addr, self._data_buf)


# SH1106 driver — same API, different page-write protocol (common on 1.3" OLEDs)
class SH1106_I2C(framebuf.FrameBuffer):
    def __init__(self, width, height, i2c, addr=0x3C):
        self.i2c = i2c
        self.addr = addr
        self.width = width
        self.height = height
        self.pages = height // 8
        self.buffer = bytearray(self.pages * width)
        super().__init__(self.buffer, width, height, framebuf.MONO_VLSB)
        self._init_display()

    def _cmd(self, *cmds):
        buf = bytearray(len(cmds) + 1)
        buf[0] = 0x00  # command mode
        for i, c in enumerate(cmds):
            buf[i + 1] = c
        self.i2c.writeto(self.addr, buf)

    def _init_display(self):
        self._cmd(
            0xAE,        # display off
            0xA8, 0x3F,  # mux ratio 64
            0xD3, 0x00,  # display offset 0
            0x40,        # start line 0
            0xA1,        # segment remap
            0xC8,        # COM scan direction
            0xDA, 0x12,  # COM pins
            0x81, 0xFF,  # contrast
            0xA4,        # entire display on (use RAM)
            0xA6,        # normal (not inverted)
            0xD5, 0x80,  # clock div
            0x8D, 0x14,  # charge pump on
            0xAF,        # display on
        )
        self.fill(0)
        self.show()

    def show(self):
        # SH1106 requires page-by-page writes with column offset 2
        col_offset = 2
        for page in range(self.pages):
            self._cmd(0xB0 | page,
                      0x00 | (col_offset & 0x0F),
                      0x10 | (col_offset >> 4))
            data = bytearray(self.width + 1)
            data[0] = 0x40
            data[1:] = self.buffer[page * self.width:(page + 1) * self.width]
            self.i2c.writeto(self.addr, data)
# --- End embedded drivers ---

i2c = I2C(
    0,
    sda=Pin(4),
    scl=Pin(5),
    freq=400_000,
)

devices = i2c.scan()
print("I2C devices:", devices)
print("Hex:", [hex(d) for d in devices])

# --- OLED test ---
OLED_ADDR = 0x3C
if OLED_ADDR not in devices:
    print(f"OLED not found at 0x{OLED_ADDR:02X}. Check wiring.")
else:
    print("OLED found, using SH1106 driver...")
    oled = SH1106_I2C(128, 64, i2c, addr=OLED_ADDR)

    # Test 1: fill white
    oled.fill(1)
    oled.show()
    time.sleep(0.5)

    # Test 2: fill black (clear)
    oled.fill(0)
    oled.show()
    time.sleep(0.5)

    # Test 3: text lines
    oled.fill(0)
    oled.text("Photobooth", 0, 0)
    oled.text("OLED OK", 0, 16)
    oled.text("128x64", 0, 32)
    oled.show()
    time.sleep(1)

    # Test 4: border rectangle
    oled.fill(0)
    oled.rect(0, 0, 128, 64, 1)
    oled.text("Border test", 8, 28)
    oled.show()
    time.sleep(1)

    # Test 5: clear and done
    oled.fill(0)
    oled.text("Test complete", 0, 28)
    oled.show()
    print("OLED test complete.")
