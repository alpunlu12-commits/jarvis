#!/usr/bin/env bash
# JARVIS Kali Linux - Kurulum & Baslatma Scripti
# Calistir: bash setup.sh

set -euo pipefail

echo ""
echo "========================================"
echo "      J.A.R.V.I.S  Kali Linux Setup"
echo "========================================"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 bulunamadi. Once Python kurulmali."
    exit 1
fi

PYTHON="$(command -v python3)"
VERSION="$($PYTHON --version 2>&1)"
echo "[OK] Python: $VERSION"

APT_PACKAGES=(
    python3
    python3-venv
    python3-pip
    python3-dev
    python3-tk
    build-essential
    portaudio19-dev
    libasound2-dev
    xdg-utils
    espeak-ng
    festival
    ffmpeg
    mpg123
    xdotool
    xclip
    wl-clipboard
    scrot
    maim
    imagemagick
    fonts-dejavu-core
)

if command -v apt-get >/dev/null 2>&1; then
    echo ""
    echo "Apt paketleri:"
    printf '  - %s\n' "${APT_PACKAGES[@]}"
    echo ""
    read -r -p "Eksik apt paketleri yuklensin mi? (e/h): " install_apt
    if [[ "$install_apt" =~ ^[eE]$ ]]; then
        if [[ "$(id -u)" -eq 0 ]]; then
            apt-get update
            apt-get install -y "${APT_PACKAGES[@]}"
        else
            sudo apt-get update
            sudo apt-get install -y "${APT_PACKAGES[@]}"
        fi
    else
        echo "Apt kurulumu atlandi. PyAudio, Tkinter, ses veya ekran araclari eksikse uygulama hata verebilir."
    fi
else
    echo "apt-get bulunamadi. Bu script Debian/Kali tabanli sistemler icindir."
fi

FONT_DIR="$(cd "$(dirname "$0")" && pwd)/Fonts"
USER_FONTS="$HOME/.local/share/fonts/jarvis"
if [[ -d "$FONT_DIR" ]]; then
    echo "[..] Fontlar kuruluyor: $USER_FONTS"
    mkdir -p "$USER_FONTS"
    cp "$FONT_DIR"/*.ttf "$USER_FONTS/" 2>/dev/null || true
    if command -v fc-cache >/dev/null 2>&1; then
        fc-cache -f "$USER_FONTS" >/dev/null 2>&1 || true
    fi
    echo "[OK] Fontlar hazir"
fi

if [[ ! -d "venv" ]]; then
    echo "[..] Virtual environment olusturuluyor..."
    "$PYTHON" -m venv venv
fi

source venv/bin/activate

if [[ ! -f "config/api_keys.json" ]]; then
    cp config/api_keys.example.json config/api_keys.json
    echo "[OK] config/api_keys.json olusturuldu. Gemini API anahtarini buraya gir."
fi

echo "[..] Python paketleri yukleniyor..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

mkdir -p "${XDG_DATA_HOME:-$HOME/.local/share}/jarvis/health"

echo ""
echo "========================================"
echo "          Kurulum Tamamlandi"
echo "========================================"
echo ""
echo "Baslatmak icin:"
echo "  source venv/bin/activate"
echo "  python main.py"
echo ""
echo "Notlar:"
echo "  - Gemini anahtari: config/api_keys.json"
echo "  - Yerel takvim: ${XDG_DATA_HOME:-$HOME/.local/share}/jarvis/calendar_events.json"
echo "  - Yerel animsaticilar: ${XDG_DATA_HOME:-$HOME/.local/share}/jarvis/reminders.json"
echo "  - Saglik export klasoru: ${XDG_DATA_HOME:-$HOME/.local/share}/jarvis/health"
echo "  - TTS varsayilan motor: espeak-ng"
echo ""

read -r -p "Simdi baslatilsin mi? (e/h): " choice
if [[ "$choice" =~ ^[eE]$ ]]; then
    python main.py
fi
