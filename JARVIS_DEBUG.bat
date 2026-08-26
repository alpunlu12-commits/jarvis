@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo [JARVIS DEBUG] Log: %~dp0run.log
python -X utf8 -u main.py > run.log 2>&1
echo.
echo [EXIT CODE: %errorlevel%]
echo --- LOG ---
type run.log
echo --- END LOG ---
pause
