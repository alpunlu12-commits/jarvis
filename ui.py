"""
JARVIS HUD UI — Tkinter, koyu tema, Stark circular HUD tarzı.

Özellikler:
- Dairesel merkez halka animasyonu (outer/inner ring, tick marks, pulsing core)
- Sol panel: Sistem durumu + Hava durumu + Saat
- Sağ panel: Conversation log
- Alt giriş çubuğu + kontrol butonları
- QR/Telefon entegrasyonu (popup)
- write_log, set_state, focus_panel, play_success_sfx, wake_up,
  wait_for_api_key, update_weather, set_phone_info
"""

from __future__ import annotations

import math
import os
import random
import threading
import time
import tkinter as tk
from collections import deque
from typing import Callable, Optional

import psutil

# ═════════════════════════════════════════════════════════════════════════════
#  Renk Paleti — Apple-design koyu HUD
# ═════════════════════════════════════════════════════════════════════════════

C_BG = "#0a0a10"
C_PANEL = "#0f1018"
C_PANEL_BORDER = "#1a2a2a"
C_PRI = "#00d4c0"          # Teal ana renk
C_PRI_DIM = "#007a6e"
C_ACCENT = "#4488ff"        # Mavi vurgu
C_GREEN = "#00ff88"
C_ORANGE = "#ff9900"
C_RED = "#ff3344"
C_GOLD = "#ffcc00"
C_TEXT = "#d0e8e6"
C_TEXT_DIM = "#5a7a78"
C_INPUT_BG = "#0c0c14"
C_HEADER_BG = "#06060c"
C_FOOTER_BG = "#06060c"

# Durum renkleri
STATE_COLORS: dict[str, str] = {
    "LISTENING": C_GREEN,
    "THINKING": C_GOLD,
    "SPEAKING": C_ACCENT,
    "ERROR": C_RED,
    "PAUSED": C_TEXT_DIM,
    "INITIALISING": C_ORANGE,
}

SYSTEM_NAME = "J.A.R.V.I.S"
MODEL_BADGE = "LOKAL · Windows"
HEADER_H = 56
FOOTER_H = 24
INPUT_H = 34
LEFT_PANEL_W = 260
RIGHT_PANEL_W = 320

# Circular HUD sabitleri
_OUTER_R = 210
_INNER_R = 175
_CORE_MIN_R = 14
_CORE_MAX_R = 28
_TICK_COUNT = 60     # Tick mark sayısı

# ═════════════════════════════════════════════════════════════════════════════
#  Ses Yöneticisi — winsound tabanlı, basit
# ═════════════════════════════════════════════════════════════════════════════

try:
    import winsound as _ws

    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False


class SoundManager:
    """Basit SFX oynatıcı — winsound backend."""

    def __init__(self) -> None:
        self._enabled: bool = True
        self._volume: float = 0.5

    def play_success(self) -> None:
        """Başarı sesi — kısa beep."""
        self._beep(880, 80)

    def play_error(self) -> None:
        """Hata sesi — çift alarm."""
        self._beep(330, 120)
        threading.Timer(0.15, lambda: self._beep(220, 180)).start()

    def play_startup(self) -> None:
        """Başlangıç sesi — ascend."""
        for freq, dur in [(440, 60), (660, 60), (880, 100)]:
            threading.Timer(
                (440 - freq + 880) * 0.0002,
                lambda f=freq, d=dur: self._beep(f, d),
            ).start()

    def _beep(self, freq: int, duration_ms: int) -> None:
        if not self._enabled or not HAS_WINSOUND:
            return
        try:
            _ws.Beep(freq, duration_ms)
        except Exception:
            pass

    def toggle(self) -> bool:
        self._enabled = not self._enabled
        return self._enabled

    @property
    def enabled(self) -> bool:
        return self._enabled


# ═════════════════════════════════════════════════════════════════════════════
#  JarvisUI — Ana HUD sınıfı
# ═════════════════════════════════════════════════════════════════════════════


class JarvisUI:
    """Tkinter tabanlı JARVIS Stark circular HUD arayüzü.

    Callback'ler:
        on_text_command(text: str)  — Kullanıcı Enter'a bastığında
        on_pause_toggle(paused: bool) — Pause durumu değiştiğinde
        on_mute_toggle(muted: bool) — Mute durumu değiştiğinde
    """

    def __init__(self) -> None:
        # ── Pencere ──────────────────────────────────────────────────────
        self.root = tk.Tk()
        self.root.title("J.A.R.V.I.S")
        self.root.configure(bg=C_BG)
        self.root.minsize(960, 640)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.W = min(max(1100, int(sw * 0.7)), sw - 40)
        self.H = min(max(700, int(sh * 0.75)), sh - 60)
        geo = f"{self.W}x{self.H}+{(sw - self.W) // 2}+{(sh - self.H) // 4}"
        self.root.geometry(geo)
        self.root.resizable(True, True)
        self._fullscreen: bool = False
        try:
            self.root.state("zoomed")
        except Exception:
            pass

        # ── Durum ────────────────────────────────────────────────────────
        self._state: str = "INITIALISING"
        self.speaking: bool = False
        self.user_speaking: bool = False
        self.muted: bool = False
        self.paused: bool = False
        self._tick: int = 0
        self._last_t: float = time.time()
        self._started_at: float = time.time()
        self._error_hold_until: float = 0.0
        self._api_key_ready: bool = True  # Lokal modda direkt True

        # ── Circular HUD açıları ─────────────────────────────────────────
        self._outer_angle: float = 0.0
        self._inner_angle: float = 0.0

        # ── QR / Telefon ─────────────────────────────────────────────────
        self._phone_url: str = ""
        self._qr_img: Optional[object] = None  # ImageTk.PhotoImage
        self._qr_toplevel: Optional[tk.Toplevel] = None

        # ── Callback'ler ─────────────────────────────────────────────────
        self.on_text_command: Optional[Callable[[str], None]] = None
        self.on_pause_toggle: Optional[Callable[[bool], None]] = None
        self.on_mute_toggle: Optional[Callable[[bool], None]] = None
        self.on_stop_command: Optional[Callable[[], None]] = None

        # ── İstatistikler ────────────────────────────────────────────────
        self._stats: dict[str, float] = {
            "cpu": 0.0, "ram": 0.0, "disk": 0.0, "battery": 100.0,
        }
        self._last_net = psutil.net_io_counters()
        self._last_net_t: float = time.time()
        self._cpu_hist: list[float] = [0.0] * 20

        # ── Ses ──────────────────────────────────────────────────────────
        self.sound = SoundManager()

        # ── Log kuyruğu (typing efekti) ─────────────────────────────────
        self._log_queue: deque[str] = deque()
        self._is_typing: bool = False

        # ── Hava durumu ─────────────────────────────────────────────────
        self._weather: dict[str, str | list[str]] = {
            "city": "—", "temp": "—", "details": ["Yükleniyor..."],
        }

        # ── Panelleri oluştur ────────────────────────────────────────────
        self._build_canvas()
        self._build_header()
        self._build_left_panel()
        self._build_right_panel()
        self._build_input_bar()
        self._build_footer()
        self._build_control_buttons()

        # ── Kısayollar ──────────────────────────────────────────────────
        self.root.bind("<Return>", self._on_submit)
        self.root.bind("<Escape>", lambda _: self._shutdown())
        self.root.bind("<F4>", lambda _: self._toggle_mute())
        self.root.bind("<F5>", lambda _: self._toggle_pause())
        self.root.bind("<F11>", lambda _: self._toggle_fullscreen())
        self.root.bind("<F>", lambda e: self._toggle_fullscreen() if e.state & 0x4 else None)

        # ── Resize -> cerceveyi yeniden ciz
        self._resize_after: str | None = None
        self.root.bind("<Configure>", self._on_resize)

        # ── Protokol & animasyon ─────────────────────────────────────────
        self.root.protocol("WM_DELETE_WINDOW", self._shutdown)
        self.root.after(100, self.sound.play_startup)
        self.root.after(300, self._animate)

    # ═════════════════════════════════════════════════════════════════════
    #  İnşaat — Widget oluşturma
    # ═════════════════════════════════════════════════════════════════════

    def _build_canvas(self) -> None:
        """Arka plan canvas — circular HUD."""
        self._canvas = tk.Canvas(
            self.root, width=self.W, height=self.H,
            bg=C_BG, highlightthickness=0,
        )
        self._canvas.place(x=0, y=0, relwidth=1.0, relheight=1.0)

    def _build_header(self) -> None:
        """Üst başlık çubuğu."""
        self._header = tk.Frame(self.root, bg=C_HEADER_BG, height=HEADER_H)
        self._header.place(x=0, y=0, relwidth=1.0, height=HEADER_H)
        self._header.pack_propagate(False)

        # Sol: model badge
        tk.Label(
            self._header, text=MODEL_BADGE, fg=C_TEXT_DIM, bg=C_HEADER_BG,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=16)

        # Orta: başlık
        tk.Label(
            self._header, text=SYSTEM_NAME, fg=C_PRI, bg=C_HEADER_BG,
            font=("Segoe UI", 20, "bold"),
        ).pack(side="left", expand=True)

        # Sağ: durum
        self._status_label = tk.Label(
            self._header, text="● INITIALISING", fg=C_ORANGE, bg=C_HEADER_BG,
            font=("Segoe UI", 10, "bold"),
        )
        self._status_label.pack(side="right", padx=16)

        # Alt çizgi
        sep = tk.Frame(self._root, bg=C_PRI_DIM, height=1) if False else tk.Frame(self.root, bg=C_PRI_DIM, height=1)
        sep.place(x=0, y=HEADER_H, relwidth=1.0)

    def _build_left_panel(self) -> None:
        """Sol panel — Sistem + Hava durumu (yarı-saydam overlay)."""
        x = 4
        y = HEADER_H + 4
        w = LEFT_PANEL_W
        h = self.H - HEADER_H - FOOTER_H - INPUT_H - 16

        self._left_panel = tk.Frame(self.root, bg=C_PANEL, bd=0,
                                    highlightthickness=1,
                                    highlightbackground=C_PANEL_BORDER)
        self._left_panel.place(x=x, y=y, width=w, height=h)

        # ── Sistem durumu kartı ──────────────────────────────────────────
        sys_frame = tk.Frame(self._left_panel, bg=C_PANEL)
        sys_frame.pack(fill="x", padx=8, pady=(8, 4))

        tk.Label(
            sys_frame, text="SYSTEM STATUS", fg=C_PRI, bg=C_PANEL,
            font=("Segoe UI", 9, "bold"), anchor="w",
        ).pack(fill="x", padx=4)

        self._sys_labels: dict[str, tuple[tk.Label, tk.Label, tk.Canvas]] = {}
        for key, label_text in [("cpu", "CPU"), ("ram", "RAM"), ("disk", "DISK"), ("battery", "BATTERY")]:
            row = tk.Frame(sys_frame, bg=C_PANEL)
            row.pack(fill="x", padx=4, pady=1)

            lbl = tk.Label(row, text=label_text, fg=C_TEXT_DIM, bg=C_PANEL,
                           font=("Segoe UI", 9), width=8, anchor="w")
            lbl.pack(side="left")

            bar = tk.Canvas(row, width=100, height=8, bg="#0a0a10",
                            highlightthickness=0)
            bar.pack(side="left", padx=(4, 8))

            val_lbl = tk.Label(row, text="0%", fg=C_TEXT, bg=C_PANEL,
                               font=("Segoe UI", 9, "bold"), width=5, anchor="e")
            val_lbl.pack(side="right")

            self._sys_labels[key] = (lbl, val_lbl, bar)

        # ── Saat ─────────────────────────────────────────────────────────
        time_frame = tk.Frame(sys_frame, bg=C_PANEL)
        time_frame.pack(fill="x", padx=4, pady=(8, 2))

        self._time_label = tk.Label(
            time_frame, text="--:--:--", fg=C_PRI, bg=C_PANEL,
            font=("Segoe UI", 16, "bold"),
        )
        self._time_label.pack(side="left")

        self._date_label = tk.Label(
            time_frame, text="—", fg=C_TEXT_DIM, bg=C_PANEL,
            font=("Segoe UI", 9),
        )
        self._date_label.pack(side="left", padx=(8, 0))

        # ── Hava durumu kartı ────────────────────────────────────────────
        sep2 = tk.Frame(self._left_panel, bg=C_PANEL_BORDER, height=1)
        sep2.pack(fill="x", padx=8, pady=6)

        weather_frame = tk.Frame(self._left_panel, bg=C_PANEL)
        weather_frame.pack(fill="x", padx=8, pady=(0, 4))

        tk.Label(
            weather_frame, text="WEATHER", fg=C_ACCENT, bg=C_PANEL,
            font=("Segoe UI", 9, "bold"), anchor="w",
        ).pack(fill="x", padx=4)

        self._weather_temp = tk.Label(
            weather_frame, text="—", fg=C_TEXT, bg=C_PANEL,
            font=("Segoe UI", 22, "bold"), anchor="w",
        )
        self._weather_temp.pack(fill="x", padx=4)

        self._weather_city = tk.Label(
            weather_frame, text="—", fg=C_TEXT_DIM, bg=C_PANEL,
            font=("Segoe UI", 9), anchor="w",
        )
        self._weather_city.pack(fill="x", padx=4)

        self._weather_details: list[tk.Label] = []
        for _ in range(3):
            lbl = tk.Label(
                weather_frame, text="", fg=C_TEXT_DIM, bg=C_PANEL,
                font=("Segoe UI", 9), anchor="w",
            )
            lbl.pack(fill="x", padx=4)
            self._weather_details.append(lbl)

        # ── QR / Telefon bölümü ──────────────────────────────────────────
        sep3 = tk.Frame(self._left_panel, bg=C_PANEL_BORDER, height=1)
        sep3.pack(fill="x", padx=8, pady=6)

        qr_frame = tk.Frame(self._left_panel, bg=C_PANEL)
        qr_frame.pack(fill="x", padx=8, pady=(0, 4))

        tk.Label(
            qr_frame, text="PHONE LINK", fg=C_GOLD, bg=C_PANEL,
            font=("Segoe UI", 9, "bold"), anchor="w",
        ).pack(fill="x", padx=4)

        self._qr_label = tk.Label(
            qr_frame, text="QR bekleniyor...", fg=C_TEXT_DIM, bg=C_PANEL,
            font=("Segoe UI", 9), anchor="w",
        )
        self._qr_label.pack(fill="x", padx=4)

        self._qr_url_label = tk.Label(
            qr_frame, text="", fg=C_PRI, bg=C_PANEL,
            font=("Segoe UI", 8), anchor="w", wraplength=LEFT_PANEL_W - 20,
        )
        self._qr_url_label.pack(fill="x", padx=4)

        self._qr_btn = tk.Button(
            qr_frame, text="TELEFON", command=self._show_qr_popup,
            fg=C_GOLD, bg=C_PANEL, activeforeground=C_BG,
            activebackground=C_GOLD, font=("Segoe UI", 9, "bold"),
            borderwidth=0, cursor="hand2",
            highlightthickness=1, highlightbackground=C_GOLD,
        )
        self._qr_btn.pack(pady=(4, 0), anchor="w", padx=4)

    def _build_right_panel(self) -> None:
        """Sağ panel — Log / Sohbet (yarı-saydam overlay)."""
        w = RIGHT_PANEL_W
        x = self.W - w - 4
        y = HEADER_H + 4
        h = self.H - HEADER_H - FOOTER_H - INPUT_H - 16

        self._right_panel = tk.Frame(self.root, bg=C_PANEL, bd=0,
                                     highlightthickness=1,
                                     highlightbackground=C_PANEL_BORDER)
        self._right_panel.place(x=x, y=y, width=w, height=h)

        tk.Label(
            self._right_panel, text="CONVERSATION", fg=C_PRI, bg=C_PANEL,
            font=("Segoe UI", 9, "bold"), anchor="w",
        ).pack(fill="x", padx=8, pady=(6, 2))

        sep = tk.Frame(self._right_panel, bg=C_PANEL_BORDER, height=1)
        sep.pack(fill="x", padx=8)

        self._log_text = tk.Text(
            self._right_panel, fg=C_TEXT, bg=C_PANEL,
            insertbackground=C_TEXT, borderwidth=0, wrap="word",
            font=("Consolas", 10), padx=8, pady=6,
            state="disabled", cursor="arrow",
        )
        self._log_text.pack(fill="both", expand=True, padx=4, pady=4)

        # Tag'ler
        self._log_text.tag_config("you", foreground="#a0f0e8")
        self._log_text.tag_config("ai", foreground=C_PRI)
        self._log_text.tag_config("sys", foreground=C_GOLD)
        self._log_text.tag_config("err", foreground=C_RED)

        # Scrollbar
        scrollbar = tk.Scrollbar(self._right_panel, command=self._log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self._log_text.config(yscrollcommand=scrollbar.set)

    def _build_input_bar(self) -> None:
        """Alt giriş çubuğu — dairenin altında ortalanmış."""
        y = self.H - INPUT_H - FOOTER_H - 4
        # Centered under the circle
        cx = self.W // 2
        input_w = 400
        x = cx - input_w // 2

        self._input_var = tk.StringVar()
        self._input_entry = tk.Entry(
            self.root, textvariable=self._input_var,
            fg=C_TEXT, bg=C_INPUT_BG, insertbackground=C_TEXT,
            borderwidth=0, font=("Consolas", 11),
            highlightthickness=1, highlightbackground=C_PANEL_BORDER,
            highlightcolor=C_PRI,
        )
        self._input_entry.place(x=x, y=y, width=input_w - 80, height=INPUT_H)

        self._send_btn = tk.Button(
            self.root, text="SEND >", command=self._on_submit,
            fg=C_ORANGE, bg=C_PANEL, activeforeground=C_BG,
            activebackground=C_ORANGE, font=("Segoe UI", 10, "bold"),
            borderwidth=0, cursor="hand2",
            highlightthickness=1, highlightbackground=C_ORANGE,
        )
        self._send_btn.place(x=x + input_w - 76, y=y, width=76, height=INPUT_H)

    def _build_footer(self) -> None:
        """Alt bilgi çubuğu."""
        y = self.H - FOOTER_H
        self._footer = tk.Frame(self.root, bg=C_FOOTER_BG, height=FOOTER_H)
        self._footer.place(x=0, y=y, relwidth=1.0, height=FOOTER_H)
        self._footer.pack_propagate(False)

        tk.Label(
            self._footer, text=f"JARVIS · {MODEL_BADGE}",
            fg=C_TEXT_DIM, bg=C_FOOTER_BG, font=("Segoe UI", 8),
        ).pack(side="left", padx=12)

        tk.Label(
            self._footer, text="[F4] MUTE  [F5] PAUSE  [ESC] EXIT",
            fg=C_TEXT_DIM, bg=C_FOOTER_BG, font=("Segoe UI", 8),
        ).pack(side="right", padx=12)

    def _build_control_buttons(self) -> None:
        """Kontrol butonları — Mute, Pause, Shutdown."""
        btn_y = self.H - INPUT_H - FOOTER_H - INPUT_H - 12
        # Center under circle
        cx = self.W // 2
        btn_x = cx - 250

        # Mute
        self._mute_btn = tk.Button(
            self.root, text="LIVE", command=self._toggle_mute,
            fg=C_GREEN, bg=C_PANEL, activeforeground=C_BG,
            activebackground=C_GREEN, font=("Segoe UI", 9, "bold"),
            borderwidth=0, cursor="hand2", width=14,
            highlightthickness=1, highlightbackground=C_GREEN,
        )
        self._mute_btn.place(x=btn_x, y=btn_y, height=28)

        # Pause
        self._pause_btn = tk.Button(
            self.root, text="PAUSE", command=self._toggle_pause,
            fg=C_ACCENT, bg=C_PANEL, activeforeground=C_BG,
            activebackground=C_ACCENT, font=("Segoe UI", 9, "bold"),
            borderwidth=0, cursor="hand2", width=14,
            highlightthickness=1, highlightbackground=C_ACCENT,
        )
        self._pause_btn.place(x=btn_x + 160, y=btn_y, height=28)

        # Settings (ayarlar / yarlar typo tolerant)
        self._settings_btn = tk.Button(
            self.root, text="AYARLAR", command=self._show_settings_popup,
            fg=C_GOLD, bg=C_PANEL, activeforeground=C_BG,
            activebackground=C_GOLD, font=("Segoe UI", 9, "bold"),
            borderwidth=0, cursor="hand2", width=10,
            highlightthickness=1, highlightbackground=C_GOLD,
        )
        self._settings_btn.place(x=btn_x + 320, y=btn_y, height=28)

        # Shutdown
        self._shutdown_btn = tk.Button(
            self.root, text="EXIT", command=self._shutdown,
            fg=C_RED, bg=C_PANEL, activeforeground=C_BG,
            activebackground=C_RED, font=("Segoe UI", 9, "bold"),
            borderwidth=0, cursor="hand2", width=8,
            highlightthickness=1, highlightbackground=C_RED,
        )
        self._shutdown_btn.place(x=btn_x + 430, y=btn_y, height=28)

    # ═════════════════════════════════════════════════════════════════════
    #  Public API
    # ═════════════════════════════════════════════════════════════════════

    def write_log(self, text: str) -> None:
        """Log paneline mesaj yaz (typing efekti ile)."""
        clean = " ".join(str(text or "").split())
        if not clean:
            return
        self._log_queue.append(clean)
        if not self._is_typing:
            self._start_typing()

    def set_state(self, state: str) -> None:
        """JARVIS durumunu güncelle."""
        prev = self._state
        self._state = state
        self.speaking = state == "SPEAKING"

        color = STATE_COLORS.get(state, C_TEXT)
        badge = "ONLINE" if state in ("LISTENING", "SPEAKING") else state.upper()
        sym = "●" if self._tick % 76 < 38 else "○"
        self.root.after(0, lambda: self._status_label.configure(
            text=f"{sym}  {badge}", fg=color,
        ))

        if state == "ERROR":
            self._error_hold_until = time.time() + 8.0
        if state != "ERROR" and prev == "THINKING":
            pass  # SFX zaten _start_typing'ta

    def focus_panel(self, section: str, duration_ms: int = 4200) -> None:
        """Panellerden birine odaklan (geçici)."""
        pass

    def play_success_sfx(self) -> None:
        """Başarı sesi çal."""
        self.root.after(0, self.sound.play_success)

    def play_error_sfx(self) -> None:
        """Hata sesi çal."""
        self.root.after(0, self.sound.play_error)

    def wake_up(self) -> None:
        """Pencereyi öne getir."""
        def _do() -> None:
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self.root.lift()
            self.root.after(3000, lambda: self.root.attributes("-topmost", False))
        self.root.after(0, _do)

    def wait_for_api_key(self) -> None:
        """API key bekler — lokal modda hemen döner."""
        self._api_key_ready = True

    def update_weather(self, city: str, temp: str, details: list[str]) -> None:
        """Hava durumu kartını güncelle."""
        self._weather = {"city": city, "temp": temp, "details": details}
        self.root.after(0, self._refresh_weather_ui)

    def set_phone_info(self, url: str, qr_image: Optional[object] = None) -> None:
        """Telefon QR bilgisini ayarla.

        Args:
            url: Telefona gösterilecek URL.
            qr_image: ImageTk.PhotoImage nesnesi (Pillow'dan).
        """
        self._phone_url = url
        self._qr_img = qr_image
        self.root.after(0, self._refresh_qr_ui)

    # ═════════════════════════════════════════════════════════════════════
    #  Private — Yardımcı methods
    # ═════════════════════════════════════════════════════════════════════

    def _refresh_qr_ui(self) -> None:
        """QR UI güncelle."""
        if self._phone_url:
            self._qr_url_label.configure(text=self._phone_url)
            self._qr_label.configure(text="Telefonunuz için QR hazır", fg=C_GREEN)
            self._qr_btn.configure(text="TELEFON", fg=C_GOLD)
        else:
            self._qr_label.configure(text="QR bekleniyor...", fg=C_TEXT_DIM)

    def _show_qr_popup(self) -> None:
        """QR popup aç/kapat toggle."""
        if self._qr_toplevel is not None:
            try:
                self._qr_toplevel.destroy()
            except Exception:
                pass
            self._qr_toplevel = None
            return

        if not self._phone_url:
            return

        tp = tk.Toplevel(self.root)
        tp.title("JARVIS — QR Kod")
        tp.configure(bg=C_BG)
        tp.geometry("340x420")
        tp.resizable(False, False)
        tp.transient(self.root)
        tp.grab_set()
        self._qr_toplevel = tp

        tk.Label(
            tp, text="Telefon Bağlantısı", fg=C_PRI, bg=C_BG,
            font=("Segoe UI", 14, "bold"),
        ).pack(pady=(16, 8))

        if self._qr_img is not None:
            qr_lbl = tk.Label(tp, image=self._qr_img, bg=C_BG)
            qr_lbl.image = self._qr_img  # Referansı koru
            qr_lbl.pack(pady=8)
        else:
            tk.Label(
                tp, text="QR mevcut değil", fg=C_TEXT_DIM, bg=C_BG,
                font=("Segoe UI", 11),
            ).pack(pady=32)

        tk.Label(
            tp, text=self._phone_url, fg=C_TEXT, bg=C_BG,
            font=("Consolas", 9), wraplength=300,
        ).pack(pady=(8, 4))

        tk.Label(
            tp, text="Bu URL'yi tarayıcınızdan açın", fg=C_TEXT_DIM, bg=C_BG,
            font=("Segoe UI", 9),
        ).pack(pady=(0, 12))

        tk.Button(
            tp, text="Kapat", command=lambda: (tp.destroy(), setattr(self, '_qr_toplevel', None)),
            fg=C_RED, bg=C_PANEL, activeforeground=C_BG,
            activebackground=C_RED, font=("Segoe UI", 10, "bold"),
            borderwidth=0, cursor="hand2", width=12,
        ).pack(pady=(0, 16))

        tp.protocol("WM_DELETE_WINDOW", lambda: (tp.destroy(), setattr(self, '_qr_toplevel', None)))

    def _start_typing(self) -> None:
        """Typing efekti ile log yaz."""
        if not self._log_queue:
            self._is_typing = False
            if self._state == "ERROR" and time.time() < self._error_hold_until:
                return
            if not self.speaking:
                self.set_state("LISTENING")
            return

        self._is_typing = True
        text = self._log_queue.popleft()
        tl = text.lower()

        if tl.startswith("siz:") or tl.startswith("you:"):
            tag = "you"
            self.user_speaking = True
        elif tl.startswith("jarvis:") or tl.startswith("ai:"):
            tag = "ai"
        elif tl.startswith("err:") or "error" in tl:
            tag = "err"
        else:
            tag = "sys"

        self._log_text.configure(state="normal")
        self._type_char(text, 0, tag)

    def _type_char(self, text: str, idx: int, tag: str) -> None:
        """Tek karakter yazarak typing efekti."""
        if idx < len(text):
            self._log_text.insert(tk.END, text[idx], tag)
            self._log_text.see(tk.END)
            self.root.after(6, self._type_char, text, idx + 1, tag)
        else:
            self._log_text.insert(tk.END, "\n")
            self._log_text.configure(state="disabled")
            self._log_text.see(tk.END)
            self.root.after(15, self._start_typing)

    def _refresh_weather_ui(self) -> None:
        """Hava durumu UI'ını yenile."""
        self._weather_temp.configure(text=str(self._weather.get("temp", "—")))
        self._weather_city.configure(text=str(self._weather.get("city", "—")))
        details = self._weather.get("details", [])
        if isinstance(details, list):
            for i, lbl in enumerate(self._weather_details):
                if i < len(details):
                    lbl.configure(text=f"• {details[i]}")
                else:
                    lbl.configure(text="")

    def _update_stats(self) -> None:
        """Sistem istatistiklerini güncelle (background thread)."""
        try:
            self._stats["cpu"] = psutil.cpu_percent(interval=None)
            self._stats["ram"] = psutil.virtual_memory().percent
            self._stats["disk"] = psutil.disk_usage("C:\\").percent
            batt = psutil.sensors_battery()
            self._stats["battery"] = batt.percent if batt else 100.0

            self._cpu_hist.pop(0)
            self._cpu_hist.append(self._stats["cpu"])
        except Exception:
            pass

    def _refresh_stats_ui(self) -> None:
        """UI'daki istatistik etiketlerini yenile."""
        colors = {
            "cpu": C_RED if self._stats["cpu"] > 80 else C_ORANGE if self._stats["cpu"] > 55 else C_GREEN,
            "ram": C_RED if self._stats["ram"] > 80 else C_ORANGE if self._stats["ram"] > 55 else C_PRI,
            "disk": C_RED if self._stats["disk"] > 85 else C_ORANGE if self._stats["disk"] > 60 else C_PRI,
            "battery": C_RED if self._stats["battery"] < 20 else C_ORANGE if self._stats["battery"] < 40 else C_GREEN,
        }
        for key, (_, val_lbl, bar) in self._sys_labels.items():
            val = self._stats[key]
            col = colors.get(key, C_TEXT)
            val_lbl.configure(text=f"{val:.0f}%", fg=col)
            # Bar çiz
            bar.delete("all")
            bar_w = int(bar["width"])
            bar_h = int(bar["height"])
            bar.create_rectangle(0, 0, bar_w, bar_h, fill="#0a0a10", outline=C_PANEL_BORDER)
            fill_w = max(1, int(bar_w * val / 100))
            bar.create_rectangle(1, 1, fill_w, bar_h - 1, fill=col, outline="")

        # Saat
        now = time.localtime()
        self._time_label.configure(text=time.strftime("%H:%M:%S", now))
        self._date_label.configure(text=time.strftime("%d %B %Y", now).upper())

    # ═════════════════════════════════════════════════════════════════════
    #  Circular HUD — Stark tarzı dairesel animasyon
    # ═════════════════════════════════════════════════════════════════════

    def _draw_circular_hud(self) -> None:
        c = self._canvas
        left = LEFT_PANEL_W + 8
        right = self.W - RIGHT_PANEL_W - 8
        cx = (left + right) // 2
        cy = HEADER_H + (self.H - HEADER_H - FOOTER_H - INPUT_H * 2 - 20) // 2
        t = self._tick

        state = "PAUSED" if self.paused else self._state
        col = STATE_COLORS.get(state, C_PRI)

        # ── Arka plan radial dots (daire içinde clip illusion) ──────────
        dot_step = 24
        for dx in range(-_OUTER_R, _OUTER_R + 1, dot_step):
            for dy in range(-_OUTER_R, _OUTER_R + 1, dot_step):
                dist = math.sqrt(dx * dx + dy * dy)
                if dist < _OUTER_R - 10 and dist > _CORE_MAX_R + 20:
                    # Only draw dots at certain distances for texture
                    if int(dist) % 48 < 4:
                        dot_alpha = max(0.15, 1.0 - dist / _OUTER_R * 0.7)
                        c.create_rectangle(
                            cx + dx, cy + dy, cx + dx + 1, cy + dy + 1,
                            fill=C_PANEL_BORDER, outline="",
                        )

        # ── Outer ring — 560px çap, 2px outline, dash, döner ───────────
        o_r = _OUTER_R
        c.create_oval(
            cx - o_r, cy - o_r, cx + o_r, cy + o_r,
            outline=C_PRI, width=2, dash=(6, 4), style="arc",
            start=self._outer_angle, extent=359.9,
        )

        # ── Inner ring — 480px çap, 1px outline, ters döner ───────────
        i_r = _INNER_R
        c.create_oval(
            cx - i_r, cy - i_r, cx + i_r, cy + i_r,
            outline=C_PRI_DIM, width=1, dash=(3, 6), style="arc",
            start=self._inner_angle, extent=359.9,
        )

        # ── Tick marks — 60 small lines around outer ring ───────────────
        for i in range(_TICK_COUNT):
            angle_rad = math.radians(i * (360 / _TICK_COUNT) + self._outer_angle)
            is_major = (i % 5 == 0)
            inner_dist = o_r - (18 if is_major else 10)
            outer_dist = o_r - 2

            x1 = cx + inner_dist * math.cos(angle_rad)
            y1 = cy + inner_dist * math.sin(angle_rad)
            x2 = cx + outer_dist * math.cos(angle_rad)
            y2 = cy + outer_dist * math.sin(angle_rad)

            tick_col = C_PRI if is_major else C_PRI_DIM
            tick_w = 2 if is_major else 1
            c.create_line(x1, y1, x2, y2, fill=tick_col, width=tick_w)

        # ── Center pulsing core ────────────────────────────────────────
        if state == "SPEAKING":
            # Pulsing: 24 -> 40
            pulse = _CORE_MIN_R + int((_CORE_MAX_R - _CORE_MIN_R) *
                                      (0.5 + 0.5 * math.sin(t * 0.2)))
        else:
            # Static at 16
            pulse = 16

        c.create_oval(
            cx - pulse, cy - pulse, cx + pulse, cy + pulse,
            fill="", outline=col, width=2,
        )

        # Inner glow
        inner_pulse = pulse - 6
        if inner_pulse > 0:
            c.create_oval(
                cx - inner_pulse, cy - inner_pulse,
                cx + inner_pulse, cy + inner_pulse,
                fill="", outline=C_PRI_DIM, width=1,
            )

        # Core dot
        c.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill=col, outline="")

        # ── Durum yazısı (daire içinde) ───────────────────────────────
        state_text = state if state != "INITIALISING" else "ONLINE" if self._tick > 60 else "INIT"
        c.create_text(
            cx, cy + 30, text=state_text, fill=col,
            font=("Segoe UI", 11, "bold"),
        )

    # ═════════════════════════════════════════════════════════════════════
    #  Ayarlar Popup
    # ═════════════════════════════════════════════════════════════════════

    def _show_settings_popup(self) -> None:
        tp = tk.Toplevel(self.root)
        tp.title("JARVIS — Ayarlar")
        tp.configure(bg=C_BG)
        tp.geometry("420x380")
        tp.resizable(False, False)
        tp.transient(self.root)
        tp.grab_set()

        tk.Label(tp, text="AYARLAR", fg=C_PRI, bg=C_BG, font=("Segoe UI", 14, "bold")).pack(pady=(16, 6))
        tk.Label(tp, text="Harf duyarliligi kapali: c=ç, s=ş, o=ö, u=ü, g=ğ, i=ı  → hepsi ayni", fg=C_TEXT_DIM, bg=C_BG, font=("Segoe UI", 9)).pack()
        tk.Label(tp, text="Örn: 'saat kac', 'cay ac', 'semsiye', 'otobus' — noktalama onemsiz", fg=C_TEXT_DIM, bg=C_BG, font=("Segoe UI", 8)).pack(pady=(0, 10))

        row = tk.Frame(tp, bg=C_BG); row.pack(fill="x", padx=16, pady=4)
        tk.Label(row, text="Mikrofon (deneysel):", fg=C_TEXT, bg=C_BG, font=("Segoe UI", 10, "bold")).pack(side="left")
        mut = "KAPALI" if self.muted else "ACIK"
        col = C_RED if self.muted else C_GREEN
        tk.Label(row, text=mut, fg=col, bg=C_BG, font=("Segoe UI", 10, "bold")).pack(side="left", padx=8)
        tk.Button(row, text="DEGISTIR", command=lambda: (self._toggle_mute(), tp.destroy(), self._show_settings_popup()), fg=C_ACCENT, bg=C_PANEL, font=("Segoe UI", 9)).pack(side="right")

        row2 = tk.Frame(tp, bg=C_BG); row2.pack(fill="x", padx=16, pady=4)
        tk.Label(row2, text="Telefon QR:", fg=C_TEXT, bg=C_BG, font=("Segoe UI", 10, "bold")).pack(side="left")
        if self._phone_url:
            tk.Label(row2, text=self._phone_url[:34] + "...", fg=C_PRI, bg=C_BG, font=("Consolas", 8)).pack(side="left", padx=8)
            tk.Button(row2, text="GOSTER", command=lambda: (tp.destroy(), self._show_qr_popup()), fg=C_GOLD, bg=C_PANEL, font=("Segoe UI", 9)).pack(side="right")
        else:
            tk.Label(row2, text="hazirlaniyor...", fg=C_TEXT_DIM, bg=C_BG, font=("Segoe UI", 9)).pack(side="left", padx=8)

        tk.Label(tp, text="Hud ortada görünmüyorsa pencereyi büyüt (ortadaki halkalar panel arasinda).", fg=C_TEXT_DIM, bg=C_BG, font=("Segoe UI", 8), wraplength=380, justify="left").pack(pady=(12, 0), padx=16)
        tk.Button(tp, text="KAPAT", command=tp.destroy, fg=C_TEXT, bg=C_PANEL, font=("Segoe UI", 10, "bold"), width=12).pack(pady=16)

    # ═════════════════════════════════════════════════════════════════════
    #  Buton Aksiyonları
    # ═════════════════════════════════════════════════════════════════════

    def _on_submit(self, event: object = None) -> None:
        """Enter basıldığında komutu işle."""
        text = self._input_var.get().strip()
        if not text:
            return
        if self.paused:
            self.write_log("SYS: Duraklatılmış durumda. Devam etmek için pause'u kapat.")
            return
        self._input_var.set("")

        # Stop komutu
        if text.lower() in ("sus", "dur", "stop", "sessiz", "kes"):
            self.write_log("SYS: Ses kesildi.")
            if self.on_stop_command:
                threading.Thread(target=self.on_stop_command, daemon=True).start()
            return

        self.write_log(f"Siz: {text}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(text,), daemon=True).start()

    def _toggle_mute(self) -> None:
        self.muted = not self.muted
        if self.muted:
            self._mute_btn.configure(text="MUTED", fg=C_RED)
            self.write_log("SYS: Mikrofon kapatildi.")
        else:
            self._mute_btn.configure(text="LIVE", fg=C_GREEN)
            self.write_log("SYS: Mikrofon acik — yazdıkların anında işlenir.")
        if self.on_mute_toggle:
            try:
                self.on_mute_toggle(self.muted)
            except Exception:
                pass

    def _toggle_pause(self) -> None:
        """Pause/Resume."""
        self.paused = not self.paused
        if self.paused:
            self._pause_btn.configure(text="RESUME", fg=C_GOLD)
            self.set_state("PAUSED")
            self.write_log("SYS: JARVIS duraklatildi.")
        else:
            self._pause_btn.configure(text="PAUSE", fg=C_ACCENT)
            self.set_state("LISTENING")
            self.write_log("SYS: JARVIS devam ediyor...")

        if self.on_pause_toggle:
            threading.Thread(target=self.on_pause_toggle, args=(self.paused,), daemon=True).start()

    def _toggle_fullscreen(self) -> None:
        self._fullscreen = not self._fullscreen
        try:
            self.root.attributes("-fullscreen", self._fullscreen)
        except Exception:
            try:
                self.root.state("zoomed" if self._fullscreen else "normal")
            except Exception:
                pass
        if hasattr(self, "on_fullscreen_toggle") and self.on_fullscreen_toggle:
            try:
                self.on_fullscreen_toggle(self._fullscreen)
            except Exception:
                pass
        self.write_log(f"SYS: Tam ekran {'acik' if self._fullscreen else 'kapali'} (F11 / ESC cikar).")
        if self._fullscreen:
            self.root.after(120, self._relayout)

    def _on_resize(self, event: object) -> None:
        if getattr(event, "widget", None) is not self.root:
            return
        if self._resize_after:
            try:
                self.root.after_cancel(self._resize_after)
            except Exception:
                pass
        self._resize_after = self.root.after(120, self._relayout)

    def _relayout(self) -> None:
        try:
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            if w < 400 or h < 300:
                return
            self.W = w
            self.H = h
            self._canvas.configure(width=w, height=h)
            try:
                self._canvas.place_configure(width=w, height=h)
            except Exception:
                pass
            x_left = 4
            y_panel = HEADER_H + 4
            panel_h = max(200, h - HEADER_H - FOOTER_H - INPUT_H - 16)
            try:
                self._left_panel.place_configure(x=x_left, y=y_panel, height=panel_h)
                self._right_panel.place_configure(x=w - RIGHT_PANEL_W - 4, y=y_panel, height=panel_h)
                cx = w // 2
                input_w = 400
                ix = max(x_left + LEFT_PANEL_W + 12, cx - input_w // 2)
                iy = h - INPUT_H - FOOTER_H - 4
                self._input_entry.place_configure(x=ix, y=iy, width=input_w - 80)
                self._send_btn.place_configure(x=ix + input_w - 76, y=iy)
                btn_y = h - INPUT_H - FOOTER_H - INPUT_H - 12
                self._mute_btn.place_configure(x=cx - 250, y=btn_y)
                self._pause_btn.place_configure(x=cx - 90, y=btn_y)
                self._shutdown_btn.place_configure(x=cx + 70, y=btn_y)
                self._footer.place_configure(y=h - FOOTER_H)
            except Exception:
                pass
        except Exception:
            pass
        finally:
            self._resize_after = None

    def _shutdown(self) -> None:
        """JARVIS'i kapat."""
        if self._qr_toplevel is not None:
            try:
                self._qr_toplevel.destroy()
            except Exception:
                pass
        self.write_log("SYS: JARVIS kapatılıyor...")
        self.root.after(400, os._exit, 0)

    # ═════════════════════════════════════════════════════════════════════
    #  Animasyon Döngüsü
    # ═════════════════════════════════════════════════════════════════════

    def _animate(self) -> None:
        """Ana animasyon döngüsü — ~30 FPS."""
        self._tick += 1
        t = self._tick

        # Açı güncelle — outer +0.5deg, inner -0.7deg per tick
        self._outer_angle += 0.5
        self._inner_angle -= 0.7

        # Wrap angles
        if self._outer_angle >= 360.0:
            self._outer_angle -= 360.0
        if self._inner_angle <= -360.0:
            self._inner_angle += 360.0

        # İstatistikleri periyodik güncelle
        if t % 60 == 0:
            threading.Thread(target=self._update_stats, daemon=True).start()
            self.root.after(10, self._refresh_stats_ui)

        # Canvas'ı temizle ve yeniden çiz
        self._canvas.delete("all")
        self._draw_circular_hud()

        self.root.after(33, self._animate)  # ~30 FPS
