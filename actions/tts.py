"""
TTS (Text-to-Speech) — Cross platform.
macOS: built-in 'say' komutu.
Windows/Linux: gTTS (Google TTS) + pygame.
"""

import subprocess
import threading
import sys
import os
import time
import tempfile

# Pygame çıktısını (Hello from pygame community) gizlemek için
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

try:
    from gtts import gTTS
    import pygame
    HAS_GTTS = True
except ImportError:
    HAS_GTTS = False

VOICE = "Yelda"  # macOS default

def speak_text(text: str, on_done=None, blocking: bool = False):
    """
    Metni sesli olarak okur.
    on_done: okuma bitince çağrılacak fonksiyon (opsiyonel)
    blocking: True ise bitene kadar bekler
    """
    if not text or not text.strip():
        if on_done:
            on_done()
        return

    # Çok uzun metinleri kısalt (TTS için)
    max_len = 500
    if len(text) > max_len:
        text = text[:max_len] + "..."

    def _run():
        try:
            if sys.platform == "darwin":
                # macOS için orijinal davranış korundu
                subprocess.run(["say", "-v", VOICE, text], check=False)
            elif HAS_GTTS:
                # Windows ve Ubuntu için Türkçe uyumlu gTTS motoru
                tmp_path = tempfile.mktemp(suffix='.mp3')
                tts = gTTS(text, lang='tr')
                tts.save(tmp_path)

                pygame.mixer.init()
                pygame.mixer.music.load(tmp_path)
                pygame.mixer.music.play()

                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)

                pygame.mixer.music.unload()
                pygame.mixer.quit()
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
        except Exception as e:
            print(f"TTS Error: {e}")
            pass

        if on_done:
            on_done()

    if blocking:
        _run()
    else:
        threading.Thread(target=_run, daemon=True).start()


def get_available_voices() -> list[str]:
    """Sistemdeki mevcut sesleri listeler."""
    if sys.platform == "darwin":
        try:
            result = subprocess.run(["say", "-v", "?"],
                                    capture_output=True, text=True)
            voices = []
            for line in result.stdout.splitlines():
                if line.strip():
                    voices.append(line.split()[0])
            return voices
        except Exception as e:
            print(f"TTS Error: {e}")
            return []
    elif HAS_GTTS:
        # gTTS için dil tabanlı ses
        return ["Google TTS (tr)"]
    return []
