"""
Lokal STT (Speech-to-Text) + wake word detection.
SpeechRecognition kutuphanesi ile Google Free Tier veya Sphinx offline.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Optional

# ── SpeechRecognition ──────────────────────────────────────────────────
try:
    import speech_recognition as sr

    HAS_SR = True
except ImportError:
    HAS_SR = False

# ── PyAudio (mikrofon erisimi) ────────────────────────────────────────
try:
    import pyaudio

    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False

# ── sabitler ───────────────────────────────────────────────────────────
_WAKE_WORD = "jarvis"
_LISTEN_TIMEOUT_SEC = 5
_PAUSE_THRESHOLD = 1.0
_ENERGY_THRESHOLD = 300


# ═══════════════════════════════════════════════════════════════════════
#  VoiceListener sinifi
# ═══════════════════════════════════════════════════════════════════════

class VoiceListener:
    """
    Lokal STT + wake word detection.
    - Google Free Tier (internet gerekli) veya Sphinx (tamamen offline)
    - Wake word: "jarvis"
    - Clap tetikleme opsiyonel (wakeup_listener modulunden entegre)
    """

    def __init__(
        self,
        on_command: Optional[Callable[[str], None]] = None,
        wake_word: str = _WAKE_WORD,
        use_offline: bool = False,
        energy_threshold: int = _ENERGY_THRESHOLD,
    ) -> None:
        """
        Args:
            on_command: Algilanan komut metni ile cagrilacak callback
            wake_word: Tetikleyici kelime (varsayilan: "jarvis")
            use_offline: True ise Sphinx kullan (internet gerekmez)
            energy_threshold: Mikrofon hassasiyet eşiği
        """
        self._on_command = on_command
        self._wake_word = wake_word.lower()
        self._use_offline = use_offline
        self._running = False
        self._energy_threshold = energy_threshold
        self._cmd_queue: queue.Queue[str] = queue.Queue()

    @staticmethod
    def is_available() -> dict[str, bool]:
        """Kutuphane durumunu dondurur."""
        return {
            "speech_recognition": HAS_SR,
            "pyaudio": HAS_PYAUDIO,
        }

    def start(self) -> str:
        """Dinlemeyi baslat. Durum mesaji dondurur."""
        if not HAS_SR:
            return "speech_recognition yuklu degil: pip install SpeechRecognition"
        if not HAS_PYAUDIO:
            return "pyaudio yuklu degil: pip install pyaudio"

        self._running = True
        threading.Thread(
            target=self._listen_loop, daemon=True, name="VoiceListener",
        ).start()
        return "dinleme baslatildi"

    def stop(self) -> None:
        """Dinlemeyi durdur."""
        self._running = False

    def get_command(self) -> Optional[str]:
        """Kuyruktan bir komut al (varsa)."""
        try:
            return self._cmd_queue.get_nowait()
        except queue.Empty:
            return None

    def wait_for_command(self, timeout: float = 30.0) -> Optional[str]:
        """Komut gelene kadar bekle."""
        try:
            return self._cmd_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _listen_loop(self) -> None:
        """Ana dinleme dongusu."""
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = self._energy_threshold
        recognizer.pause_threshold = _PAUSE_THRESHOLD

        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)

        while self._running:
            try:
                self._listen_once(recognizer)
            except Exception as exc:
                print(f"[VoiceListener] Dinleme hatasi: {exc}")
                time.sleep(1)

    def _listen_once(self, recognizer: "sr.Recognizer") -> None:
        """Tek bir dinleme dongusu."""
        try:
            with sr.Microphone() as source:
                audio = recognizer.listen(
                    source, timeout=_LISTEN_TIMEOUT_SEC, phrase_time_limit=10,
                )
        except sr.WaitTimeoutInfoError:
            return  # Timeout — normal, tekrar dinle
        except Exception:
            return

        # Metne cevir
        text = self._transcribe(audio)
        if not text:
            return

        text_lower = text.lower()

        # Wake word kontrolu
        if self._wake_word in text_lower:
            # Wake word'den sonraki kismi komut olarak al
            idx = text_lower.find(self._wake_word)
            command = text[idx + len(self._wake_word):].strip()
            if command:
                self._cmd_queue.put(command)
                if self._on_command:
                    self._on_command(command)
            else:
                # Sadece "jarvis" dedi — hazir mod
                self._cmd_queue.put("[WAKE]")
                if self._on_command:
                    self._on_command("[WAKE]")

    def _transcribe(self, audio: "sr.AudioData") -> Optional[str]:
        """AudioData'y metne cevir."""
        try:
            if self._use_offline:
                return recognizer_sphinx(audio)
            return recognizer_google(audio)
        except Exception:
            # Google basarisizsa offline dene
            try:
                return recognizer_sphinx(audio)
            except Exception:
                return None


# ═══════════════════════════════════════════════════════════════════════
#  Transkripsiyon fonksiyonlari
# ═══════════════════════════════════════════════════════════════════════

def recognizer_google(audio: "sr.AudioData", language: str = "tr-TR") -> Optional[str]:
    """Google Speech Recognition (ucretsiz, internet gerekli)."""
    if not HAS_SR:
        return None
    recognizer = sr.Recognizer()
    try:
        return recognizer.recognize_google(audio, language=language)
    except sr.UnknownValueInfoError:
        return None
    except sr.RequestError:
        return None


def recognizer_sphinx(audio: "sr.AudioData", language: str = "tr-TR") -> Optional[str]:
    """CMU Sphinx (tamamen offline). Turkce sinirli destek."""
    if not HAS_SR:
        return None
    recognizer = sr.Recognizer()
    try:
        # Sphinx varsayilan olarak Ingilizce — Turkce modeli varsa kullan
        return recognizer.recognize_sphinx(audio, language=language)
    except sr.UnknownValueInfoError:
        return None
    except Exception:
        # Sphinx Turkce desteklemiyorsa Ingilizce dene
        try:
            return recognizer.recognize_sphinx(audio)
        except Exception:
            return None
