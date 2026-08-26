@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo [JARVIS] Baslatiliyor... (kapatmak icin HUD'da ESC veya bu pencereyi kapat)
python -X utf8 -u main.py
if errorlevel 1 (
  echo.
  echo [HATA] JARVIS kapandi, kod: %errorlevel%
  echo Log: %~dp0run.log
  pause
)
