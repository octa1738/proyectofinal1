"""Genera el ejecutable de Windows con PyInstaller.

Resultado: dist/MediaDownloader/MediaDownloader.exe
(copia la carpeta COMPLETA dist/MediaDownloader si queres llevarla a otra PC)
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Instalando PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    import static_ffmpeg

    static_ffmpeg.add_paths()
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        sys.exit("No se encontro FFmpeg. Ejecuta primero Instalar_Librerias.bat")

    sep = ";" if sys.platform.startswith("win") else ":"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed",
        "--name", "MediaDownloader",
        "--collect-all", "customtkinter",
        "--collect-submodules", "yt_dlp",
        "--add-binary", f"{ffmpeg}{sep}ffmpeg_bin",
        "--add-binary", f"{ffprobe}{sep}ffmpeg_bin",
    ]
    icon = ROOT / "assets" / "icon.ico"
    if icon.exists():
        cmd += ["--icon", str(icon)]
    cmd.append(str(ROOT / "app.py"))

    print("Compilando (puede tardar unos minutos)...")
    subprocess.check_call(cmd, cwd=ROOT)
    print("\nListo: dist/MediaDownloader/MediaDownloader.exe")


if __name__ == "__main__":
    main()
