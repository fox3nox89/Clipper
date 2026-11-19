@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Clipper
if not exist .venv (
    echo Bitte zuerst setup.bat doppelklicken.
    pause
    exit /b
)
echo Clipper laeuft. Fenster offen lassen. Beenden: dieses Fenster schliessen.
echo Fertige Clips liegen in: %~dp0clips
echo.
:loop
.venv\Scripts\python -m clipper run
echo.
echo Clipper wurde beendet. Neustart in 30 Sekunden ... (Fenster schliessen zum Beenden)
timeout /t 30 /nobreak >nul
goto loop
