@echo off
:: ═══════════════════════════════════════════════════════════════════════════
::  JARVIS Kurulum — Windows
:: ═══════════════════════════════════════════════════════════════════════════

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   J.A.R.V.I.S  —  Kurulum Başlatılıyor  ║
echo  ╚══════════════════════════════════════════╝
echo.

:: Python kontrolü
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [HATA] Python bulunamadı! Python 3.10+ gerekli.
    echo        https://www.python.org/downloads/
    pause
    exit /b 1
)

:: pip ile bağımlılıkları kur
echo [1/3] Bağımlılıklar kuruluyor...
pip install -r requirements.txt --quiet
if %ERRORLEVEL% neq 0 (
    echo [UYARI] pip install hatası — bazı özellikler çalışmayabilir.
)

:: pyaudio kurulumu (Windows'ta bazen sorunlu)
echo [2/3] PyAudio kontrol ediliyor...
python -c "import pyaudio" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [INFO] PyAudio bulunamadı — pip install pyaudio deneyin.
    echo        Gerekirse wheel indirin: https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio
)

:: Config oluştur (yoksa)
echo [3/3] Config kontrol ediliropython -c "from pathlib import Path; p=Path('config/api_keys.json'); p.parent.mkdir(exist_ok=True); p.write_text('{\"offline_mode\": true}') if not p.exists() else None"

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   Kurulum tamamlandı!                    ║
echo  ║   Başlamak için: python main.py          ║
echo  ╚══════════════════════════════════════════╝
echo.
pause
