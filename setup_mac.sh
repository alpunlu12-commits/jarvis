#!/bin/bash
# JARVIS macOS — Kurulum & Başlatma Scripti
# Çalıştır: bash setup_mac.sh

set -e

echo ""
echo "╔══════════════════════════════════════╗"
echo "║     J.A.R.V.I.S  macOS Kurulum      ║"
echo "╚══════════════════════════════════════╝"
echo ""

if ! xcode-select -p &>/dev/null; then
    echo "🔧 Xcode Command Line Tools kuruluyor (bu birkaç dakika sürebilir)..."
    xcode-select --install
else
    echo "✅ Xcode Command Line Tools kurulu"
fi

PYTHON=$(which python3)
echo "✅ Python: $($PYTHON --version 2>&1)"

if ! command -v brew &>/dev/null; then
    echo "⚠️  Homebrew bulunamadı. Lütfen kurun."
fi

if ! brew list portaudio &>/dev/null 2>&1; then
    echo "📦 PortAudio kuruluyor..."
    brew install portaudio
fi

PORTAUDIO_PREFIX=$(brew --prefix portaudio 2>/dev/null || echo "")
if [ -n "$PORTAUDIO_PREFIX" ]; then
    export CFLAGS="-I$PORTAUDIO_PREFIX/include ${CFLAGS:-}"
    export LDFLAGS="-L$PORTAUDIO_PREFIX/lib ${LDFLAGS:-}"
fi

if [ ! -d "venv" ]; then
    echo "📦 Virtual environment oluşturuluyor..."
    $PYTHON -m venv venv
fi

source venv/bin/activate

if [ ! -f "config/api_keys.json" ]; then
    mkdir -p config
    cp config/api_keys.example.json config/api_keys.json 2>/dev/null || echo '{"gemini_api_key": "", "voice": "Charon"}' > config/api_keys.json
fi

echo "📦 Paketler yükleniyor..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo "🚀 Kurulum tamamlandı! Başlatılıyor..."
python main.py
