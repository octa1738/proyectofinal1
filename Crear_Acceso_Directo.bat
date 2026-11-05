@echo off
rem Crea un acceso directo "Media Downloader" en el escritorio.
rem (No copies el .bat solo: usa este acceso directo.)
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Media Downloader.lnk'); $s.TargetPath='%~dp0iniciar_app.bat'; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; $s.Description='Media Downloader'; $s.Save()"

if %errorlevel%==0 (
    echo.
    echo Listo: se creo "Media Downloader" en tu escritorio.
) else (
    echo.
    echo No se pudo crear el acceso directo.
)
echo.
pause
