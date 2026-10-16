@echo off
echo ======================================
echo       J.A.R.V.I.S  Windows Kurulum
echo ======================================
echo.

python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Python kurulu degil. Lutfen Python 3.10+ kurun ve PATH'e eklediginizden emin olun.
    pause
    goto :eof
)

if not exist venv\ (
    echo Virtual environment olusturuluyor...
    python.exe -m venv venv
)

call venv\Scripts\activate.bat

if not exist config\api_keys.json (
    if not exist config\ mkdir config
    if exist config\api_keys.example.json (
        copy config\api_keys.example.json config\api_keys.json
    ) else (
        echo {"gemini_api_key": "", "voice": "Charon"} > config\api_keys.json
    )
)

echo Paketler yukleniyor...
python.exe -m pip install --upgrade pip -q
pip install -r requirements.txt -q
pip install pyaudio -q

echo Kurulum tamamlandi! Baslatiliyor...
python.exe main.py
pause
