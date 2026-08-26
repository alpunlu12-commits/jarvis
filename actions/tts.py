"""
TTS (Text-to-Speech) — Turkce optimize.
Oncelik sirasi: edge-tts (neural TR) > pyttsx3 (Turkce ses varsa) > PowerShell SAPI > espeak.
edge-tts: Microsoft Edge neural voices (ucretsiz, API keysiz, internet gerekli)
  tr-TR-EmelNeural (kadin, dogal) / tr-TR-AhmetNeural (erkek)
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

try:
    import pyttsx3

    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False

try:
    import edge_tts  # type: ignore[import-not-found]

    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

_MAX_TEXT_LENGTH = 500
_TTS_TIMEOUT_SEC = 60
_EDGE_VOICE_DEFAULT = "tr-TR-EmelNeural"
_EDGE_VOICE_ALT = "tr-TR-AhmetNeural"
EDGE_VOICES: dict[str, str] = {
    "emel": "tr-TR-EmelNeural",
    "ahmet": "tr-TR-AhmetNeural",
    "kadin": "tr-TR-EmelNeural",
    "erkek": "tr-TR-AhmetNeural",
    "female": "tr-TR-EmelNeural",
    "male": "tr-TR-AhmetNeural",
}


def _get_configured_voice() -> str:
    try:
        from jarvis.config.app_config import get_app_config_value

        v = str(get_app_config_value("tts_voice", _EDGE_VOICE_DEFAULT) or "").strip()
        if v in EDGE_VOICES.values():
            return v
        if v.lower() in EDGE_VOICES:
            return EDGE_VOICES[v.lower()]
        if v:
            return v
    except Exception:
        pass
    # fallback: direct file read
    try:
        import json as _js
        from pathlib import Path as _P
        p = _P(__file__).resolve().parent.parent / "config" / "api_keys.json"
        if p.exists():
            raw = _js.loads(p.read_text(encoding="utf-8"))
            v2 = str(raw.get("tts_voice", "") or "").strip()
            if v2:
                return v2
    except Exception:
        pass
    return _EDGE_VOICE_DEFAULT


def set_tts_voice(name: str) -> str:
    key = (name or "").strip().lower()
    voice_id = EDGE_VOICES.get(key)
    if not voice_id:
        if name in EDGE_VOICES.values():
            voice_id = name
        else:
            return f"Bilinmeyen ses: {name}. Mevcut: emel (kadin), ahmet (erkek)"
    try:
        from jarvis.config.app_config import save_app_config

        save_app_config({"tts_voice": voice_id})
    except Exception:
        pass
    return f"Ses degistirildi: {voice_id} ({'Emel' if 'Emel' in voice_id else 'Ahmet'})"


def get_current_voice() -> str:
    return _get_configured_voice()


# ═══════════════════════════════════════════════════════════════════════
#  pyttsx3 backend
# ═══════════════════════════════════════════════════════════════════════

def _find_turkish_voice_id() -> Optional[str]:
    if not HAS_PYTTSX3:
        return None
    try:
        engine = pyttsx3.init()
        voices = engine.getProperty("voices") or []
        for v in voices:
            name = (v.name or "").lower()
            vid = (v.id or "").lower()
            langs = " ".join(str(x).lower() for x in getattr(v, "languages", []) or [])
            if "tr-tr" in name or "turkish" in name or "turkce" in name or "tr-tr" in vid or "tr_tr" in langs:
                engine.stop()
                return v.id
        engine.stop()
    except Exception:
        pass
    return None


def _speak_edge_tts(text: str, voice: str = _EDGE_VOICE_DEFAULT) -> bool:
    if not HAS_EDGE_TTS:
        return False
    try:
        async def _gen() -> str:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            tmp.close()
            communicate = edge_tts.Communicate(text, voice)  # type: ignore[attr-defined]
            await communicate.save(tmp.name)
            return tmp.name

        mp3_path = asyncio.run(_gen())
        try:
            return _play_mp3(mp3_path)
        finally:
            try:
                os.unlink(mp3_path)
            except Exception:
                pass
    except Exception:
        return False


def _play_mp3(path: str) -> bool:
    p = Path(path)
    if not p.exists():
        return False
    try:
        import pygame  # type: ignore[import-not-found]

        pygame.mixer.init()
        pygame.mixer.music.load(str(p))
        pygame.mixer.music.play()
        import time as _time

        while pygame.mixer.music.get_busy():
            _time.sleep(0.1)
        pygame.mixer.quit()
        return True
    except Exception:
        pass
    try:
        ps = (
            "Add-Type -AssemblyName presentationCore; "
            f"$m = New-Object System.Windows.Media.MediaPlayer; "
            f"$m.Open([uri]'{p.as_posix()}'); $m.Play(); "
            "Start-Sleep -Seconds 1; "
            "while($m.Position -lt $m.NaturalDuration.TimeSpan -and $m.NaturalDuration.HasTimeSpan){Start-Sleep -Milliseconds 200} "
        )
        result = subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps],
            check=False,
            timeout=_TTS_TIMEOUT_SEC,
        )
        return result.returncode == 0
    except Exception:
        return False
    return False


def _speak_pyttsx3(text: str, voice: Optional[str] = None, rate: Optional[int] = None) -> bool:
    if not HAS_PYTTSX3:
        return False
    try:
        engine = pyttsx3.init()
        target_voice = voice or _find_turkish_voice_id()
        if target_voice:
            engine.setProperty("voice", target_voice)
        if rate is not None:
            engine.setProperty("rate", rate)
        else:
            try:
                cur = engine.getProperty("rate")
                engine.setProperty("rate", int(cur * 0.92))
            except Exception:
                pass
        engine.say(text)
        engine.runAndWait()
        engine.stop()
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════
#  PowerShell SAPI backend
# ═══════════════════════════════════════════════════════════════════════

def _speak_powershell_sapi(text: str) -> bool:
    """PowerShell System.Speech.Synthesis ile konus."""
    try:
        safe_text = text.replace("'", "''").replace('"', '`"')
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Speak('{safe_text}')"
        )
        result = subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-Command", script],
            check=False,
            timeout=_TTS_TIMEOUT_SEC,
        )
        return result.returncode == 0
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════
#  espeak backend (Linux/cross-platform fallback)
# ═══════════════════════════════════════════════════════════════════════

def _speak_espeak(text: str) -> bool:
    """espeak-ng veya espeak ile konus (fallback)."""
    espeak_cmd = shutil.which("espeak-ng") or shutil.which("espeak")
    if not espeak_cmd:
        return False
    try:
        subprocess.run(
            [espeak_cmd, "-v", "tr", text],
            check=True,
            timeout=_TTS_TIMEOUT_SEC,
        )
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════
#  Ana fonksiyon
# ═══════════════════════════════════════════════════════════════════════

def speak(
    text: str,
    voice: Optional[str] = None,
    blocking: bool = True,
    on_done: Optional[Callable[[], None]] = None,
) -> str:
    """
    Metni sesli olarak oku. Lokal TTS backend'lerini sirayla dener.

    Oncelik: pyttsx3 > PowerShell SAPI > espeak

    Args:
        text: Okunacak metin
        voice: Sapi/voice adi (opsiyonel, pyttsx3 icin)
        blocking: True ise bitene kadar bekle
        on_done: Bitince cagrilacak callback

    Returns:
        Kullanilan backend adi veya hata mesaji
    """
    if not text or not text.strip():
        if on_done:
            on_done()
        return "bos"

    if len(text) > _MAX_TEXT_LENGTH:
        text = text[:_MAX_TEXT_LENGTH] + "..."

    def _run() -> str:
        eff_voice = voice or _get_configured_voice()
        if _speak_edge_tts(text, voice=eff_voice):
            return "edge-tts"

        if _speak_pyttsx3(text, voice=voice):
            return "pyttsx3"

        if _speak_powershell_sapi(text):
            return "powershell_sapi"

        if _speak_espeak(text):
            return "espeak"

        return "hata: TTS backend bulunamadi"

    def _threaded() -> None:
        _run()
        if on_done:
            on_done()

    if blocking:
        result = _run()
        if on_done:
            on_done()
        return result
    else:
        threading.Thread(target=_threaded, daemon=True, name="TTS").start()
        return "baslatildi"


def get_available_voices() -> list[str]:
    """Mevcut TTS seslerini listele (pyttsx3 varsa)."""
    if not HAS_PYTTSX3:
        return ["pyttsx3 yuklu degil — pip install pyttsx3"]

    try:
        engine = pyttsx3.init()
        voices = engine.getProperty("voices")
        names = [v.name for v in voices] if voices else []
        engine.stop()
        return names
    except Exception as exc:
        return [f"Ses listesi alinamadi: {exc}"]


def get_tts_info() -> dict[str, bool]:
    espeak_available = bool(shutil.which("espeak-ng") or shutil.which("espeak"))
    try:
        import pygame  # type: ignore[import-not-found]

        has_pygame = True
    except ImportError:
        has_pygame = False
    return {
        "edge_tts": HAS_EDGE_TTS,
        "pygame": has_pygame,
        "pyttsx3": HAS_PYTTSX3,
        "powershell_sapi": True,
        "espeak": espeak_available,
    }
