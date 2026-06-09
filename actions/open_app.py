
"""
Uygulama açma — Cross-platform
"""

import subprocess
import shutil
import sys
import os

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
        if sys.platform == "darwin":
            result = subprocess.run(["open", "-a", resolved], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return f"{resolved} açıldı."
            result2 = subprocess.run(["open", resolved], capture_output=True, text=True, timeout=10)
            if result2.returncode == 0:
                return f"{app_name} açıldı."
            return f"'{app_name}' bulunamadı veya açılamadı."

        elif sys.platform == "win32":
            # Windows'ta start komutu
            try:
                os.startfile(resolved)
                return f"{resolved} açıldı."
            except FileNotFoundError:
                result = subprocess.run(f"start \"\" \"{resolved}\"", shell=True, capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    return f"{resolved} açıldı."
                return f"'{app_name}' bulunamadı veya açılamadı."

        elif sys.platform.startswith("linux"):
            # Ubuntu'da uygulamayı çalıştırılabilir adıyla aramayı dene
            linux_aliases = {
                "google chrome": "google-chrome",
                "visual studio code": "code",
                "system settings": "gnome-control-center",
                "calculator": "gnome-calculator",
                "terminal": "gnome-terminal"
            }
            linux_resolved = linux_aliases.get(resolved.lower(), resolved.lower().replace(" ", "-"))

            # Arka planda çalıştır
            subprocess.Popen([linux_resolved], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"{resolved} açıldı."

    except subprocess.TimeoutExpired:
        return f"'{app_name}' açılırken zaman aşımı."
    except Exception as e:
        return f"Hata: {e}"
