"""Plays a short click sound (e.g. for a countdown tick).

The source is typically a longer mp3 (e.g. timer.mp3) where only the opening
transient is the "click". On first use we decode the mp3 with pydub/ffmpeg,
trim it to `duration_ms`, and cache it as a wav file, since Windows'
`winsound` can only play wav but does so reliably (unlike the legacy MCI
mpegvideo driver, which silently no-ops on modern Windows).
"""

from __future__ import annotations

import ctypes
import warnings
import winsound
from pathlib import Path

import imageio_ffmpeg

# pydub warns that ffmpeg/avconv aren't on PATH before we override the converter below
with warnings.catch_warnings():
    warnings.simplefilter("ignore", RuntimeWarning)
    from pydub import AudioSegment

AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()

# winsound.PlaySound refuses SND_MEMORY|SND_ASYNC together even though winmm supports
# it; call PlaySoundA directly to avoid per-play file I/O (and its latency jitter).
_winmm = ctypes.windll.winmm
_winmm.PlaySoundA.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32)
_winmm.PlaySoundA.restype = ctypes.c_int
_SND_MEMORY = 0x0004
_SND_ASYNC = 0x0001
_SND_NODEFAULT = 0x0002


class ClickSound:
    """Plays the trimmed opening of an audio file, asynchronously and repeatably."""

    def __init__(self, path: str | Path, duration_ms: int = 150) -> None:
        self._wav_bytes: bytes | None = None
        source = Path(path)
        if not source.exists():
            print(f"[ClickSound] File not found: {source}")
            return

        cache_path = source.with_name(f"_click_cache_{duration_ms}ms.wav")
        try:
            if not cache_path.exists():
                # codec="mp3" skips pydub's ffprobe-based metadata lookup (we only bundle ffmpeg)
                clip = AudioSegment.from_file(source, format="mp3", codec="mp3")[:duration_ms]
                clip.export(cache_path, format="wav")
            # keep the wav in memory so play() never touches disk (avoids I/O-latency drift)
            self._wav_bytes = cache_path.read_bytes()
        except Exception as exc:
            print(f"[ClickSound] Could not prepare click clip from {source}: {exc}")

    def play(self) -> None:
        """Play the click. Non-blocking; overlaps/replaces any click still playing."""
        if self._wav_bytes is None:
            return
        _winmm.PlaySoundA(self._wav_bytes, None, _SND_MEMORY | _SND_ASYNC | _SND_NODEFAULT)

    def close(self) -> None:
        winsound.PlaySound(None, winsound.SND_PURGE)

    def __enter__(self) -> "ClickSound":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
