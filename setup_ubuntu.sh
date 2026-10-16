#!/bin/bash
# JARVIS Ubuntu (Linux) — Kurulum & Başlatma Scripti
# Çalıştır: bash setup_ubuntu.sh

set -e

echo ""
echo "╔══════════════════════════════════════╗"
echo "║    J.A.R.V.I.S  Ubuntu Kurulum      ║"
echo "╚══════════════════════════════════════╝"
echo ""

echo "🔧 Sistem paketleri güncelleniyor ve bağımlılıklar kuruluyor (sudo yetkisi gerekebilir)..."
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip portaudio19-dev xdotool espeak

PYTHON=$(which python3)
echo "✅ Python: $($PYTHON --version 2>&1)"

if [ ! -d "venv" ]; then
    echo "📦 Virtual environment oluşturuluyor..."
    $PYTHON -m venv venv
fi

source venv/bin/activate

if [ ! -f "config/api_keys.json" ]; then
    mkdir -p config
    cp config/api_keys.example.json config/api_keys.json 2>/dev/null || echo '{"gemini_api_key": "", "voice": "Charon"}' > config/api_keys.json
fi

echo "📦 Python paketleri yükleniyor..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo "🚀 Kurulum tamamlandı! Başlatılıyor..."
python main.py
