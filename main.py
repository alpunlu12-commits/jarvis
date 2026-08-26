#!/usr/bin/env python3
"""
JARVIS Main — Orkestrasyon dosyası.
Config yükle, memory yükle, engine parse et, tool'ları çağır, TTS ile cevap ver, UI'ı güncelle.

Dual mode:
  - GEMINI_API_KEY varsa → Gemini Live (opsiyonel, opsiyonel import)
  - Yoksa → Lokal engine + voice listener + wakeup
"""

from __future__ import annotations

import datetime
import os
import sys
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass
import threading
import traceback
from pathlib import Path
from typing import Any

# ── Proje kök dizini ────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# ── Config & Memory ─────────────────────────────────────────────────────
from config.app_config import get_app_config_value, has_gemini_api_key, load_app_config
from memory.memory_manager import delete_memory, load_memory, update_memory

# ── Engine (lokal intent parsing) ────────────────────────────────────────
from core.engine import ParsedCommand, parse_command

# ── UI ──────────────────────────────────────────────────────────────────
from ui import JarvisUI

# ── Actions ─────────────────────────────────────────────────────────────
from actions.open_app import open_app
from actions.sys_info import get_system_info
from actions.browser import browser_control
from actions.shell import shell_run
from actions.weather import get_weather
from actions.media import open_youtube_search, open_spotify_search
from actions.health import get_health_score
from actions.tts import get_current_voice, set_tts_voice, speak

# ── Voice (opsiyonel) ──────────────────────────────────────────────────
try:
    from voice.listener import VoiceListener
    HAS_VOICE = True
except ImportError:
    HAS_VOICE = False

# ── Wake listener ───────────────────────────────────────────────────────
from wakeup_listener import WakeGestureListener

# ── Phone Server (lokal QR kontrol) ──────────────────────────────────────
try:
    from server.phone_server import PhoneServer
    HAS_PHONE_SERVER = True
except ImportError:
    HAS_PHONE_SERVER = False
    PhoneServer = None  # type: ignore

# ═══════════════════════════════════════════════════════════════════════════
#  TOOL_MAP — Engine intent → action fonksiyonu eşleme
# ═══════════════════════════════════════════════════════════════════════════

TOOL_MAP: dict[str, dict[str, Any]] = {
    "open_app": {
        "fn": lambda args: open_app(args.get("app_name", "")),
        "desc": "Uygulama açma",
    },
    "sys_info": {
        "fn": lambda args: get_system_info(args.get("info_type", args.get("query", "all"))),
        "desc": "Sistem bilgisi",
    },
    "get_weather": {
        "fn": lambda args: get_weather(args.get("location")),
        "desc": "Hava durumu",
    },
    "browser_control": {
        "fn": lambda args: browser_control(
            args.get("action", "search"), args.get("url"), args.get("query"),
        ),
        "desc": "Tarayıcı kontrolü",
    },
    "shell_run": {
        "fn": lambda args: shell_run(args.get("command", "")),
        "desc": "Shell komutu",
    },
    "play_media": {
        "fn": lambda args: open_youtube_search(args.get("query", "")),
        "desc": "Medya oynatma",
    },
    "save_memory": {
        "fn": lambda args: _save_memory_tool(args),
        "desc": "Hafıza kaydetme",
    },
    "delete_memory": {
        "fn": lambda args: delete_memory(
            args.get("category", ""), args.get("key", ""), args.get("match_text", ""),
        ),
        "desc": "Hafıza silme",
    },
    "analyze_screen": {
        "fn": lambda args: _not_available("Ekran analizi (Vision modülü gerekli)"),
        "desc": "Ekran analizi",
    },
    "health": {
        "fn": lambda args: get_health_score(args.get("query", "overall")),
        "desc": "Sağlık özeti",
    },
    "selamla": {
        "fn": lambda args: _selamla(),
        "desc": "Selamlaşma",
    },
    "set_voice": {
        "fn": lambda args: _set_voice_tool(args),
        "desc": "Ses degisimi",
    },
    "chat": {
        "fn": lambda args: args.get("response", "Anlayamadım."),
        "desc": "Sohbet",
    },
}


def _save_memory_tool(args: dict[str, Any]) -> str:
    """Memory kaydetme wrapper."""
    cat = args.get("category", "notes")
    key = args.get("key", "")
    val = args.get("value", "")
    content = args.get("content", "")

    # Engine'den gelen content formatında kaydet
    if content and not key:
        key = content[:40].replace(" ", "_")
        val = content

    if key and val:
        update_memory({cat: {key: {"value": val}}})
        return f"Hafızaya kaydedildi: {cat}/{key}"
    return "Kaydedilecek bilgi yok."


def _selamla() -> str:
    """Rastgele selam döndür."""
    import random
    selamlar = [
        "Merhaba! Size nasıl yardımcı olabilirim?",
        "Selam! JARVIS hazır, emrinize amade.",
        "Hoş geldiniz! Bugün size nasıl yardımcı olabilirim?",
        "Merhaba! Sizi dinliyorum.",
    ]
    return random.choice(selamlar)


def _set_voice_tool(args: dict[str, Any]) -> str:
    req = str(args.get("voice", "")).strip().lower()
    if req == "toggle":
        cur = get_current_voice()
        req = "ahmet" if "Emel" in cur else "emel"
    result = set_tts_voice(req)
    return result


def _not_available(msg: str) -> str:
    return f"[Bilgi] {msg} — bu özellik şu an aktif değil."


# ═══════════════════════════════════════════════════════════════════════════
#  JarvisOrchestrator — Ana orkestrasyon sınıfı
# ═══════════════════════════════════════════════════════════════════════════


class JarvisOrchestrator:
    """JARVIS orkestrasyon — UI, engine, tool, TTS entegrasyonu."""

    def __init__(self, ui: JarvisUI) -> None:
        self.ui = ui
        self._config = load_app_config()
        self._memory = load_memory()
        self._voice_listener: Any = None
        self._wake_listener: Any = None
        self._phone_server: Any = None
        self._tts_busy = False

        self.ui.on_text_command = self._on_text_command
        self.ui.on_pause_toggle = self._on_pause_toggle
        self.ui.on_mute_toggle = self._on_mute_toggle
        self.ui.on_fullscreen_toggle = self._on_fullscreen_toggle

    def start(self) -> None:
        self.ui.write_log("SYS: JARVIS baslatiliyor...")
        self.ui.set_state("INITIALISING")

        threading.Thread(target=self._load_weather, daemon=True).start()

        self.ui.write_log("SYS: YAZARAK KONUS — alttaki kutuya yaz + ENTER.")
        self.ui.write_log("SYS: Mikrofon icin HUD'da LIVE'a bas (F4) — izin isteyecek.")
        self.ui.write_log("SYS: TIP: c/s/o/u/g yazsan da olur — 'semsiyeyi ac', 'cay yap', 'otobus' hepsini anlarim.")

        # Phone server — lokal QR kontrol
        self._start_phone_server()

        # Durumu güncelle
        self.ui.set_state("LISTENING")
        self.ui.write_log("SYS: JARVIS hazır. Dinliyorum...")
        self.ui.write_log("SYS: Komutlarınızı bekliyorum. 'Merhaba' diyerek başlayabilirsiniz.")

    def _start_voice_listener(self) -> None:
        """Sesli dinleyiciyi başlat."""
        try:
            self._voice_listener = VoiceListener(
                on_command=self._on_voice_command,
                wake_word="jarvis",
            )
            result = self._voice_listener.start()
            if "hata" in result.lower():
                self.ui.write_log(f"SYS: Voice listener başlatılamadı — {result}")
            else:
                self.ui.write_log("SYS: 🎤 Sesli dinleme aktif.")
        except Exception as e:
            self.ui.write_log(f"SYS: Voice listener hatası: {e}")

    def _start_wake_listener(self) -> None:
        """Çift alkış wake listener'ı başlat."""
        try:
            if WakeGestureListener.is_available():
                self._wake_listener = WakeGestureListener(on_wake=self.ui.wake_up)
                self._wake_listener.start()
                self.ui.write_log("SYS: 👏 Çift alkış tetikleyici aktif.")
            else:
                self.ui.write_log("SYS: Wake listener pyaudio gerektirir.")
        except Exception as e:
            self.ui.write_log(f"SYS: Wake listener hatası: {e}")

    def _load_weather(self) -> None:
        """Hava durumunu arka planda yükle."""
        try:
            result = get_weather()
            if result:
                self._parse_and_update_weather(result)
        except Exception:
            pass

    def _parse_and_update_weather(self, text: str) -> None:
        """Hava durumu metnini parse edip UI'a gönder."""
        if not text or "alınamadı" in text.lower():
            self.ui.update_weather("—", "—", ["Veri yok"])
            return

        # Basit parse: "Istanbul için: 28°C, Güneşli, ..."
        prefix, _, body = text.partition(":")
        city = "Istanbul"
        if "için" in prefix:
            city = prefix.split("için")[0].strip().title()

        parts = [p.strip(" .") for p in body.split(",") if p.strip()]
        temp = parts[0] if parts else "—"
        details = parts[1:4] if len(parts) > 1 else ["Anlık veri hazır."]

        self.ui.update_weather(city, temp, details)

    # ═════════════════════════════════════════════════════════════════════
    #  Komut İşleme
    # ═════════════════════════════════════════════════════════════════════

    def _on_text_command(self, text: str) -> None:
        """Metin komutu işlendiğinde çağrılır."""
        if self.ui.paused:
            return

        self.ui.set_state("THINKING")

        try:
            parsed = parse_command(text)
            self._execute_and_respond(parsed)
        except Exception as e:
            self.ui.write_log(f"ERR: Komut işlenirken hata: {e}")
            self.ui.set_state("ERROR")
            traceback.print_exc()

    def _on_voice_command(self, text: str) -> None:
        """Sesli komut işlendiğinde çağrılır."""
        if text == "[WAKE]":
            self.ui.write_log("SYS: 🎤 Uyandım! Komut bekliyorum...")
            return
        if self.ui.paused or self.ui.muted:
            return

        self.ui.write_log(f"Siz (ses): {text}")
        self.ui.set_state("THINKING")

        try:
            parsed = parse_command(text)
            self._execute_and_respond(parsed)
        except Exception as e:
            self.ui.write_log(f"ERR: Sesli komut hatası: {e}")
            self.ui.set_state("ERROR")

    def _on_pause_toggle(self, paused: bool) -> None:
        pass

    def _on_mute_toggle(self, muted: bool) -> None:
        if muted:
            if self._voice_listener:
                try:
                    self._voice_listener.stop()
                except Exception:
                    pass
                self._voice_listener = None
            self.ui.write_log("SYS: Mikrofon kapatildi.")
            return
        if not HAS_VOICE:
            self.ui.write_log("SYS: Ses kutuphanesi yok (pip install PyAudio / SpeechRecognition). Yazarak devam et.")
            return
        try:
            self.ui.write_log("SYS: Ses dinleme deneniyor (pyaudio)...")
            self._start_voice_listener()
        except Exception as e:
            self.ui.write_log(f"SYS: Ses acilamadi: {e} — yazarak devam et.")

    def _on_fullscreen_toggle(self, enabled: bool) -> None:
        pass

    def _execute_and_respond(self, parsed: ParsedCommand) -> None:
        """Parsed komutu çalıştır ve cevap üret."""
        intent = parsed.intent
        args = dict(parsed.args)
        confidence = parsed.confidence

        print(f"[JARVIS] 🔧 {intent} (conf={confidence:.2f}) {args}")

        # Tool'ı bul ve çalıştır
        tool_info = TOOL_MAP.get(intent)
        if not tool_info:
            self.ui.write_log(f"ERR: Bilinmeyen intent: {intent}")
            self.ui.set_state("ERROR")
            return

        try:
            result = tool_info["fn"](args)
            result_str = str(result or "Tamam.")
        except Exception as e:
            result_str = f"Hata: {e}"
            self.ui.write_log(f"ERR: {intent} — {result_str}")
            self.ui.set_state("ERROR")
            self.ui.play_error_sfx()
            return

        # Sonucu log'a yaz
        self.ui.write_log(f"JARVIS: {result_str}")

        # Başarı SFX'i
        if intent in ("open_app", "save_memory", "selamla"):
            self.ui.play_success_sfx()

        # TTS ile sesli cevap (arka planda)
        self._speak_async(result_str)

        # Hava durumu panelini güncelle
        if intent == "get_weather":
            self._parse_and_update_weather(result_str)

        # Durumu dinleme moduna çevir
        self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {intent} → {result_str[:80]}")

    # ═════════════════════════════════════════════════════════════════════
    #  TTS
    # ═════════════════════════════════════════════════════════════════════

    def _speak_async(self, text: str) -> None:
        """TTS'yi arka planda çalıştır."""
        if self.ui.muted or self._tts_busy:
            return

        def _run() -> None:
            self._tts_busy = True
            self.ui.set_state("SPEAKING")
            try:
                speak(text, blocking=True)
            except Exception:
                pass
            finally:
                self._tts_busy = False
                self.ui.set_state("LISTENING")

        threading.Thread(target=_run, daemon=True, name="TTS").start()

    def _handle_phone_command(self, text: str) -> str:
        txt = (text or "").strip()
        if not txt:
            return "Bos komut."
        try:
            parsed = parse_command(txt)
            tool_info = TOOL_MAP.get(parsed.intent)
            if not tool_info:
                return f"Bilinmeyen komut: {parsed.intent}"
            result = tool_info["fn"](dict(parsed.args))
            result_str = str(result or "Tamam.")
            try:
                self.ui.write_log(f"PHONE: {txt} -> {result_str[:120]}")
            except Exception:
                pass
            if parsed.intent == "get_weather":
                try:
                    self._parse_and_update_weather(result_str)
                except Exception:
                    pass
            self._speak_async(result_str)
            return result_str
        except Exception as e:
            return f"Hata: {e}"

    def _start_phone_server(self) -> None:
        if not HAS_PHONE_SERVER or PhoneServer is None:
            self.ui.write_log("SYS: Phone server modulu bulunamadi.")
            return
        try:
            self._phone_server = PhoneServer(command_handler=self._handle_phone_command)
            self._phone_server.start()
            import time
            time.sleep(0.6)
            if not self._phone_server.is_running:
                self.ui.write_log("SYS: Phone server baslatilamadi.")
                return
            url = self._phone_server.get_url()
            ws_url = self._phone_server.get_ws_url()
            self.ui.write_log(f"SYS: Phone Control aktif -> {url}")
            self.ui.write_log(f"SYS: QR tarat -> {ws_url[:60]}...")
            qr_image = None
            try:
                png_bytes = self._phone_server.get_qr_image_bytes()
                if png_bytes:
                    from PIL import Image, ImageTk
                    import io
                    pil = Image.open(io.BytesIO(png_bytes))
                    pil = pil.resize((160, 160), Image.NEAREST)
                    qr_image = ImageTk.PhotoImage(pil)
            except Exception:
                pass
            try:
                self.ui.set_phone_info(url, qr_image)
            except Exception:
                pass
        except Exception as e:
            self.ui.write_log(f"SYS: Phone server hatasi: {e}")

    def shutdown(self) -> None:
        """Tüm kaynakları temizle."""
        if self._phone_server:
            try:
                self._phone_server.stop()
            except Exception:
                pass
        if self._voice_listener:
            try:
                self._voice_listener.stop()
            except Exception:
                pass
        if self._wake_listener:
            try:
                self._wake_listener.stop()
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════
#  Entry Point
# ═══════════════════════════════════════════════════════════════════════════


def main() -> None:
    """JARVIS'i başlat — UI + Orchestrator."""
    # Windows cp1254 Unicode fix
    try:
        import sys
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    print("[JARVIS] Baslatiliyor...")
    print(f"[JARVIS] Proje dizini: {BASE_DIR}")

    # Gemini kontrolü
    if has_gemini_api_key():
        print("[JARVIS] Gemini API anahtari bulundu - Live mod mevcut.")
    else:
        print("[JARVIS] Gemini API anahtari yok - Lokal mod aktif.")

    # UI oluştur
    ui = JarvisUI()

    # Orchestrator oluştur ve başlat
    orchestrator = JarvisOrchestrator(ui)

    def _run_orchestrator() -> None:
        ui.wait_for_api_key()
        orchestrator.start()

    threading.Thread(target=_run_orchestrator, daemon=True).start()

    # Kapatma callback'i
    def _on_close() -> None:
        orchestrator.shutdown()
        ui._shutdown()

    ui.root.protocol("WM_DELETE_WINDOW", _on_close)

    # Mainloop
    print("[JARVIS] HUD baslatildi.")
    ui.root.mainloop()

    print("[JARVIS] Kapatildi.")


if __name__ == "__main__":
    main()
