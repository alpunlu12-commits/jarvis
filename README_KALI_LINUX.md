# JARVIS Kali Linux Surumu

Bu kopya macOS bagimliliklari kaldirilmis Kali/Debian Linux surumudur.
-BAGWELPOWER-

## Kurulum

```bash
cd jarvis-kali-linux
bash setup.sh
```

Elle kurulum icin apt paketleri:

```bash
sudo apt-get update
sudo apt-get install -y \
  python3 python3-venv python3-pip python3-dev python3-tk \
  build-essential portaudio19-dev libasound2-dev \
  xdg-utils espeak-ng festival ffmpeg mpg123 \
  xdotool xclip wl-clipboard scrot maim imagemagick \
  fonts-dejavu-core
```

Python paketleri:

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Baslatma

```bash
source venv/bin/activate
python main.py
```

Gemini API anahtarini `config/api_keys.json` icindeki `gemini_api_key` alanina yaz.

## Linux Eslesmeleri

- `osascript` / AppleScript kaldirildi.
- macOS `open` yerine `xdg-open` kullanildi.
- macOS `say` yerine `espeak-ng` / `espeak`, opsiyonel `festival` ve `gTTS` fallback eklendi.
- macOS `afplay` yerine `ffplay`, `mpg123`, `cvlc` veya `play` denenir.
- `pbcopy` yerine `wl-copy`, `xclip`, `xsel` veya `pyperclip` denenir.
- Ekran goruntusu icin Swift helper yerine `maim+xdotool`, `scrot`, `xfce4-screenshooter`, `gnome-screenshot`, `grim` ve Pillow fallback kullanilir.
- Apple Calendar/Reminders yerine yerel JSON depolari kullanilir.

## Veri Yollari

Varsayilan Linux veri kok dizini:

```text
~/.local/share/jarvis/
```

Dosyalar:

- Takvim: `~/.local/share/jarvis/calendar_events.json`
- Animsaticilar: `~/.local/share/jarvis/reminders.json`
- Saglik export: `~/.local/share/jarvis/health/HealthAutoExport-YYYY-MM-DD.json`

Ortam degiskenleri:

- `JARVIS_DATA_DIR`: tum JARVIS veri dizinini degistirir.
- `JARVIS_HEALTH_DIR`: saglik export klasorunu degistirir.
- `JARVIS_HEALTH_FILE`: tek bir saglik JSON dosyasi belirtir.
- `JARVIS_TTS_BACKEND`: `auto`, `espeak`, `festival`, `gtts`.
- `JARVIS_TTS_VOICE`: espeak sesi, varsayilan `tr`.

## Notlar

- WhatsApp otomatik gonderim Linux'ta xdotool/PyAutoGUI ile best-effort calisir. En stabil akış telefon numarasi veya kayitli kisi numarasi ile WhatsApp Web taslagi acmaktir.
- Wayland oturumunda ekran goruntusu masaustu izinlerine bagli olabilir. X11 oturumunda `maim`, `scrot` ve `xdotool` daha stabil calisir.
