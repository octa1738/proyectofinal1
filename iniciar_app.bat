@echo off
cd /d "%~dp0"

set PY=python
set PYW=pythonw
where py >nul 2>nul
if %errorlevel%==0 (
    set PY=py -3
    set PYW=pyw -3
)

%PY% -c "import customtkinter, yt_dlp, static_ffmpeg" >nul 2>nul
if not %errorlevel%==0 (
    echo Faltan librerias. Ejecuta primero Instalar_Librerias.bat
    echo.
    pause
    exit /b 1
)

start "" %PYW% app.py
