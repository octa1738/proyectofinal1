@echo off
title Instalador de librerias - Media Downloader
cd /d "%~dp0"

set PY=python
where py >nul 2>nul
if %errorlevel%==0 set PY=py -3

%PY% --version >nul 2>nul
if not %errorlevel%==0 (
    echo.
    echo No se encontro Python en este equipo.
    echo Instalalo desde https://www.python.org/downloads/
    echo IMPORTANTE: marca la casilla "Add python.exe to PATH" al instalar.
    echo.
    pause
    exit /b 1
)

echo Instalando librerias necesarias (puede tardar unos minutos)...
echo.
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if not %errorlevel%==0 (
    echo.
    echo Hubo un error instalando las librerias. Revisa tu conexion a internet.
    pause
    exit /b 1
)

echo.
echo Descargando FFmpeg (solo la primera vez)...
%PY% -c "import static_ffmpeg; static_ffmpeg.add_paths(); print('FFmpeg listo')"

echo.
echo Todo listo. Ahora abri la app con iniciar_app.bat
echo.
pause
