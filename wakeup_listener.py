"""
Cift alkis tetikleyici — JARVIS wake-up gesture.
2 saniye icinde 2 alkis -> on_wake() cagirir.

Iyilestirmeler (referansa karsi):
- PyAudio error handling (deviceBusy, overflow)
- Esik degeri dinamik ayarlanabilir
- Graceful shutdown (stream cleanup garanti)
- Thread-safe start/stop
"""

from __future__ import annotations

import math
import struct
import threading
import time
from typing import Callable, Optional

try:
    import pyaudio

    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False

# ── varsayilanlar ──────────────────────────────────────────────────────
SAMPLE_RATE = 16000
CHUNK = 1024  # ~64 ms/kare
DEFAULT_CLAP_THRESHOLD = 1800  # Int16 RMS esigi
CLAP_MIN_GAP = 0.12  # Ayni alkisin cercevelere yayilmasini onler
CLAP_WINDOW = 2.0  # Iki alkis bu kadar saniye icinde olmali


def _rms(data: bytes) -> float:
    """Ses verisinden Root Mean Square hesapla."""
    count = len(data) // 2
    if count == 0:
        return 0.0
    shorts = struct.unpack(f"{count}h", data)
    return math.sqrt(sum(s * s for s in shorts) / count)


class WakeGestureListener:
    """
    Cift alkis ile tetiklenen wake-up listener.

    Ornek:
        def on_wake():
            print("Uyandim!")

        listener = WakeGestureListener(on_wake)
        listener.start()
        # ...
        listener.stop()
    """

    def __init__(
        self,
        on_wake: Callable[[], None],
        clap_threshold: int = DEFAULT_CLAP_THRESHOLD,
        clap_window: float = CLAP_WINDOW,
        device_index: Optional[int] = None,
    ) -> None:
        """
        Args:
            on_wake: Cift alkis algilaninca cagrilacak fonksiyon
            clap_threshold: RMS esigi (dusuk = daha hassas)
            clap_window: Iki alkis arasindaki max sure (saniye)
            device_index: Mikrofon device index (None = varsayilan)
        """
        self._on_wake = on_wake
        self._clap_threshold = clap_threshold
        self._clap_window = clap_window
        self._device_index = device_index
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @staticmethod
    def is_available() -> bool:
        """PyAudio yuklu mu?"""
        return HAS_PYAUDIO

    def start(self) -> str:
        """Dinlemeyi baslat. Durum mesaji dondurur."""
        if not HAS_PYAUDIO:
            return "pyaudio yuklu degil: pip install pyaudio"
        if self._running:
            return "zaten calisiyor"

        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="WakeClap",
        )
        self._thread.start()
        return "wake listener baslatildi"

    def stop(self) -> None:
        """Dinlemeyi durdur ve kaynaklari temizle."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    @property
    def is_running(self) -> bool:
        return self._running

    def _loop(self) -> None:
        pa: Optional[pyaudio.PyAudio] = None
        stream: Optional[pyaudio.Stream] = None

        try:
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK,
                input_device_index=self._device_index,
            )

            clap_times: list[float] = []

            while self._running:
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                except IOError:
                    continue  # Overflow — atla, devam et

                rms_val = _rms(data)
                now = time.monotonic()

                # Pencere disi eski alkislari temizle
                clap_times = [t for t in clap_times if now - t < self._clap_window]

                if rms_val > self._clap_threshold:
                    # Ayni alkisin tekrarlanmasini onle
                    if not clap_times or (now - clap_times[-1]) > CLAP_MIN_GAP:
                        clap_times.append(now)
                        print(f"[Wake] Alkis #{len(clap_times)} (RMS: {rms_val:.0f})")

                        if len(clap_times) >= 2:
                            clap_times = []
                            print("[Wake] Cift alkis — tetikleniyor")
                            try:
                                self._on_wake()
                            except Exception as exc:
                                print(f"[Wake] Callback hatasi: {exc}")

        except Exception as exc:
            print(f"[Wake] Kritik hata: {exc}")
        finally:
            # Graceful cleanup — garanti
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            if pa is not None:
                try:
                    pa.terminate()
                except Exception:
                    pass
