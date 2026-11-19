@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Clipper - Einrichtung
echo ============================================
echo.

set NEEDS_RESTART=0

where python >nul 2>nul
if errorlevel 1 (
    echo [1/3] Python fehlt - wird installiert ...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    set NEEDS_RESTART=1
) else (
    echo [1/3] Python ist installiert.
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [2/3] ffmpeg fehlt - wird installiert ...
    winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
    set NEEDS_RESTART=1
) else (
    echo [2/3] ffmpeg ist installiert.
)

if "%NEEDS_RESTART%"=="1" (
    echo.
    echo Programme wurden installiert.
    echo Bitte dieses Fenster schliessen und setup.bat NOCH EINMAL doppelklicken.
    pause
    exit /b
)

echo [3/3] Installiere das Tool ...
if not exist .venv (
    python -m venv .venv || goto :error
)
.venv\Scripts\python -m pip install --upgrade pip -q
.venv\Scripts\python -m pip install -r requirements.txt -q || goto :error

if not exist config.yaml (
    copy config.example.yaml config.yaml >nul
    echo config.yaml wurde angelegt.
)

echo.
echo ============================================
echo   Fertig!
echo   1. Gleich oeffnet sich config.yaml im Editor.
echo      Setze "enabled: true" bei deinen Kampagnen-Streamern
echo      und speichere mit Strg+S.
echo   2. Danach start.bat doppelklicken.
echo ============================================
pause
notepad config.yaml
exit /b

:error
echo.
echo FEHLER - bitte einen Screenshot von diesem Fenster an Claude schicken.
pause
