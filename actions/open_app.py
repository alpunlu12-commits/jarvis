"""
Uygulama açma — Sadece whitelisted uygulamalar, shell=False, timeout 10s.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional


# ── Whitelist ─────────────────────────────────────────────────────────────────
# Değer: (exe adı, cool)
# cool=True ise PATH'ten çalıştırılır, cool=False ise os.startfile ile URI scheme açılır.

APP_ALIASES: dict[str, tuple[str, bool]] = {
    # Tarayıcılar
    "edge":              ("msedge", True),
    "microsoft edge":    ("msedge", True),
    "chrome":            ("chrome", True),
    "google chrome":     ("chrome", True),
    "firefox":           ("firefox", True),
    # Geliştirme araçları
    "vscode":            ("code", True),
    "vs code":           ("code", True),
    "code":              ("code", True),
    # Editör / Not
    "notepad":           ("notepad", True),
    "notlar":            ("notepad", True),
    "not defteri":       ("notepad", True),
    "wordpad":           ("wordpad", True),
    # Terminal
    "terminal":          ("cmd", True),
    "cmd":               ("cmd", True),
    "powershell":        ("pwsh", True),
    # Dosya yöneticisi
    "explorer":          ("explorer", True),
    "dosya gezgini":     ("explorer", True),
    "file explorer":     ("explorer", True),
    # Office
    "word":              ("winword", True),
    "excel":             ("excel", True),
    "powerpoint":        ("powerpnt", True),
    # Medya
    "spotify":           ("Spotify", True),
    "notion":            ("Notion", True),
    # İletişim
    "discord":           ("Discord", True),
    "slack":             ("Slack", True),
    "whatsapp":          ("WhatsApp", True),
    "telegram":          ("Telegram", True),
    "zoom":              ("Zoom", True),
    # Yardımcılar
    "calculator":        ("calc", True),
    "hesap makinesi":    ("calc", True),
    "paint":             ("mspaint", True),
    "snipping tool":     ("SnippingTool", True),
    "ekran alıntısı":    ("SnippingTool", True),
    "task manager":      ("taskmgr", True),
    "görev yöneticisi":  ("taskmgr", True),
}

# URI scheme'leri sadece bu listedekilerle açılır (arbitrary URL değil)
URI_SCHEMES: dict[str, str] = {
    "ayarlar":          "ms-settings:",
    "settings":         "ms-settings:",
    "photos":           "ms-photos:",
    "fotoğraflar":      "ms-photos:",
    "mail":             "outlookmail:",
    "calendar":         "outlookcal:",
    "takvim":           "outlookcal:",
    "store":            "ms-windows-store:",
    "mağaza":           "ms-windows-store:",
    "music":            "mswindowsmusic:",
    "müzik":            "mswindowsmusic:",
    "maps":             "bingmaps:",
    "haritalar":        "bingmaps:",
}

TIMEOUT_SECONDS: int = 10


def _validate_executable(name: str) -> Optional[str]:
    """Whitelist'teki bir executable'ı PATH'te doğrula. Path traversal engeli."""
    if "/" in name or "\\" in name:
        return None
    if ".." in name:
        return None
    path = shutil.which(name)
    if path and os.path.isfile(path):
        return path
    return None


def open_app(app_name: str) -> str:
    """
    Whitelisted bir uygulamayı aç.

    Args:
        app_name: Kullanıcının belirttiği uygulama adı (Türkçe/İngilizce).

    Returns:
        İşlem sonucu mesajı.
    """
    if not app_name or not app_name.strip():
        return "Uygulama adı belirtilmedi."

    normalized = app_name.lower().strip()

    # 1) URI scheme kontrolü (ayarlar, photos vb.)
    if normalized in URI_SCHEMES:
        return _open_uri_scheme(URI_SCHEMES[normalized], app_name)

    # 2) Whitelist kontrolü
    if normalized not in APP_ALIASES:
        safe_apps = sorted(set(v[0] for v in APP_ALIASES.values()))
        return (
            f"'{app_name}' whitelist'te değil. "
            f"Mevcut uygulamalar: {', '.join(safe_apps[:15])}..."
        )

    exe_name, _ = APP_ALIASES[normalized]

    # 3) URI scheme ise
    if normalized in URI_SCHEMES:
        return _open_uri_scheme(URI_SCHEMES[normalized], app_name)

    # 4) PATH'te executable ara
    exe_path = _validate_executable(exe_name)
    if exe_path:
        return _open_subprocess(exe_path, app_name)

    return f"'{app_name}' ({exe_name}) sistemde bulunamadı."


def _open_subprocess(exe_path: str, app_name: str) -> str:
    """subprocess.run ile güvenli şekilde uygulama aç."""
    try:
        result = subprocess.run(
            [exe_path],
            shell=False,
            timeout=TIMEOUT_SECONDS,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return f"{app_name} açıldı."
        return f"{app_name} açılırken hata oluştu (kod: {result.returncode})."
    except subprocess.TimeoutExpired:
        return f"{app_name} açılırken zaman aşımı oluştu ({TIMEOUT_SECONDS}s)."
    except FileNotFoundError:
        return f"'{app_name}' çalıştırılamadı: dosya bulunamadı."
    except OSError as e:
        return f"'{app_name}' çalıştırılamadı: {e}"


def _open_uri_scheme(scheme: str, app_name: str) -> str:
    """Windows URI scheme'i güvenli şekilde aç."""
    if not scheme.endswith(":"):
        return f"Geçersiz URI scheme: {scheme}"
    try:
        os.startfile(scheme)
        return f"{app_name} açıldı."
    except OSError as e:
        return f"'{app_name}' ({scheme}) açılamadı: {e}"
