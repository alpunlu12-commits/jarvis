"""
Uygulama açma — macOS 'open' komutu ile çalışır.
Alp Ünlü tarafından yapılmıştır — @alppunlu
"""

import subprocess
import shutil


# Kısa isimden uygulama yoluna eşleme
APP_ALIASES = {
    "safari":      "Safari",
    "chrome":      "Google Chrome",
    "firefox":     "Firefox",
    "terminal":    "Terminal",
    "iterm":       "iTerm",
    "iterm2":      "iTerm",
    "finder":      "Finder",
    "spotify":     "Spotify",
    "vscode":      "Visual Studio Code",
    "vs code":     "Visual Studio Code",
    "code":        "Visual Studio Code",
    "xcode":       "Xcode",
    "notion":      "Notion",
    "slack":       "Slack",
    "discord":     "Discord",
    "whatsapp":    "WhatsApp",
    "telegram":    "Telegram",
    "zoom":        "zoom.us",
    "mail":        "Mail",
    "calendar":    "Calendar",
    "takvim":      "Calendar",
    "notes":       "Notes",
    "notlar":      "Notes",
    "music":       "Music",
    "müzik":       "Music",
    "photos":      "Photos",
    "fotoğraflar": "Photos",
    "maps":        "Maps",
    "haritalar":   "Maps",
    "calculator":  "Calculator",
    "hesap makinesi": "Calculator",
    "system preferences": "System Preferences",
    "system settings": "System Settings",
    "ayarlar":     "System Settings",
    "activity monitor": "Activity Monitor",
    "aktivite monitörü": "Activity Monitor",
    "preview":     "Preview",
    "önizleme":    "Preview",
    "textedit":    "TextEdit",
    "numbers":     "Numbers",
    "pages":       "Pages",
    "keynote":     "Keynote",
    "figma":       "Figma",
    "postman":     "Postman",
    "docker":      "Docker",
    "sequel pro":  "Sequel Pro",
    "tableplus":   "TablePlus",
}


def open_app(app_name: str) -> str:
    """Uygulamayı açar, başarı/hata mesajı döndürür."""
    if not app_name:
        return "Uygulama adı belirtilmedi."

    normalized = app_name.lower().strip()
    resolved   = APP_ALIASES.get(normalized, app_name)

    try:
        result = subprocess.run(
            ["open", "-a", resolved],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return f"{resolved} açıldı."
        else:
            # Spotlight ile dene
            result2 = subprocess.run(
                ["open", resolved],
                capture_output=True, text=True, timeout=10
            )
            if result2.returncode == 0:
                return f"{app_name} açıldı."
            return f"'{app_name}' bulunamadı veya açılamadı."
    except subprocess.TimeoutExpired:
        return f"'{app_name}' açılırken zaman aşımı."
    except Exception as e:
        return f"Hata: {e}"
