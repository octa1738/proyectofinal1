@echo off
title Crear ejecutable - Media Downloader
cd /d "%~dp0"

set PY=python
where py >nul 2>nul
if %errorlevel%==0 set PY=py -3

%PY% -c "import customtkinter, yt_dlp, static_ffmpeg" >nul 2>nul
if not %errorlevel%==0 (
    echo Faltan librerias. Ejecuta primero Instalar_Librerias.bat
    pause
    exit /b 1
)

%PY% build_exe.py
echo.
echo Si todo salio bien, el programa esta en la carpeta dist\MediaDownloader
pause
