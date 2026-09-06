"""Host-side serial interface for the Pico OLED display."""

from __future__ import annotations

import time

import serial


class OledDisplay:
    """Sends display commands to the Pico over USB serial.

    Fails silently if the Pico is not connected so the app works without it.
    """

    def __init__(self, port: str, baud: int = 115200) -> None:
        self._connected = False
        self._buf = ""
        try:
            self._serial = serial.Serial(
                port,
                baud,
                timeout=1,
                dsrdtr=False,
                rtscts=False,
            )
            # Wait for the Pico to finish booting main.py, then flush any boot noise
            time.sleep(2.0)
            self._serial.reset_input_buffer()
            self._connected = True
            print(f"[OLED] Connected on {port}")
        except Exception as exc:
            print(f"[OLED] Could not connect to {port}: {exc}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_button(self) -> bool:
        """Return True if the Pico has reported a button press since last call."""
        if not self._connected:
            return False
        try:
            waiting = self._serial.in_waiting
            if waiting > 0:
                self._buf += self._serial.read(waiting).decode(errors="ignore")
            if "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                return line.strip() == "BUTTON_PRESS"
        except Exception:
            pass
        return False

    def clear(self) -> None:
        self._send("CLEAR")

    def idle(self) -> None:
        self._send("IDLE")

    def countdown(self, photo_num: int, total: int, seconds: int) -> None:
        status = f"Photo {photo_num} of {total}"
        self._send(f"COUNTDOWN:{seconds}:{status}")

    def check_countdown_done(self) -> bool:
        """Non-blocking check for a queued "COUNTDOWN_DONE" ack from the Pico.

        Lets a caller pump other work (e.g. a camera preview loop) while
        waiting, instead of blocking like countdown_sync().
        """
        if not self._connected:
            return False
        try:
            waiting = self._serial.in_waiting
            if waiting > 0:
                self._buf += self._serial.read(waiting).decode(errors="ignore")
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                if line.strip() == "COUNTDOWN_DONE":
                    return True
        except Exception:
            pass
        return False

    def countdown_sync(self, photo_num: int, total: int, seconds: int, timeout: float = 2.0) -> None:
        """Like countdown(), but blocks until the Pico reports it finished drawing.

        The Pico's per-second animation can occasionally run long; waiting for
        its "COUNTDOWN_DONE" ack (rather than assuming it takes exactly 1s)
        keeps a click/tick sound in sync with what's actually on screen.
        Falls back to returning after `timeout` if no ack arrives (e.g. not connected).
        """
        self.countdown(photo_num, total, seconds)
        if not self._connected:
            return
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.check_countdown_done():
                return
            time.sleep(0.005)

    def done(self) -> None:
        self._send("DONE")

    def animate(self, frames: int, delay_ms: int = 100) -> None:
        """Show a built-in animation on the Pico OLED."""
        self._send(f"ANIMATE:{frames}:{delay_ms}")

    def error(self, message: str) -> None:
        """Display an error message on the OLED."""
        self._send(f"ERROR:{message[:64]}")

    def flush_input(self) -> None:
        """Discard any buffered serial data (e.g. stray button presses during a session)."""
        if not self._connected:
            return
        try:
            self._serial.reset_input_buffer()
        except Exception:
            pass
        self._buf = ""

    def close(self) -> None:
        if self._connected:
            try:
                self._serial.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _send(self, msg: str) -> None:
        if not self._connected:
            return
        try:
            self._serial.write(f"{msg}\n".encode())
            self._serial.flush()
        except Exception as exc:
            print(f"[OLED] Send error: {exc}")
            self._connected = False
