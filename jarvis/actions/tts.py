"""
TTS (Text-to-Speech) — macOS built-in 'say' komutu kullanır.
Ek kurulum gerektirmez, Türkçe ve İngilizce destekler.
Alp Ünlü tarafından yapılmıştır — @alppunlu
"""

import subprocess
import threading


# macOS'taki Türkçe ses: 'Yelda' (macOS 13+) veya 'Zoe' (İngilizce)
# Kullanılabilir sesleri görmek için: say -v ?
VOICE = "Yelda"    # Türkçe yoksa "Zoe" veya "Samantha" kullanılır


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
            subprocess.run(["say", "-v", VOICE, text], check=False)
        except FileNotFoundError:
            # 'say' bulunamazsa sessiz geç
            pass
        if on_done:
            on_done()

    if blocking:
        _run()
    else:
        threading.Thread(target=_run, daemon=True).start()


def get_available_voices() -> list[str]:
    """macOS'taki mevcut sesleri listeler."""
    try:
        result = subprocess.run(["say", "-v", "?"],
                                capture_output=True, text=True)
        voices = []
        for line in result.stdout.splitlines():
            if line.strip():
                voices.append(line.split()[0])
        return voices
    except Exception:
        return []
