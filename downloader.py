"""Motor de descarga y conversion (backend) del Media Downloader.

Usa yt-dlp para descargar y FFmpeg (provisto por static-ffmpeg, o incluido
dentro del .exe) para convertir a MP3, unir video + audio, recortar y
incrustar la portada.
"""

import os
import re
import shutil
import sys
import threading
from pathlib import Path

import yt_dlp
from yt_dlp.utils import download_range_func

# --------------------------------------------------------------- calidades
AUDIO_BITRATE_MAP = {
    "320 kbps": "320",
    "256 kbps": "256",
    "192 kbps": "192",
    "128 kbps": "128",
}

VIDEO_QUALITY_MAP = {
    "Mejor disponible": None,
    "1080p (Full HD)": 1080,
    "720p (HD)": 720,
    "480p": 480,
    "360p": 360,
}

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class DownloadCancelled(Exception):
    """Se lanza cuando el usuario cancela la descarga."""


class _SilentLogger:
    """Logger mudo para que yt-dlp no escriba nada en consola."""

    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


# ------------------------------------------------------------------ FFmpeg
def _bundled_ffmpeg_dir():
    """Carpeta con ffmpeg dentro del .exe (PyInstaller), si existe."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        folder = Path(base) / "ffmpeg_bin"
        if folder.exists():
            return folder
    return None


def ensure_ffmpeg_available():
    """Localiza ffmpeg y ffprobe. Si no estan, static-ffmpeg los descarga
    la primera vez (requiere internet) y los agrega al PATH."""
    bundled = _bundled_ffmpeg_dir()
    if bundled:
        current = os.environ.get("PATH", "")
        if str(bundled) not in current:
            os.environ["PATH"] = str(bundled) + os.pathsep + current

    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return True
    try:
        import static_ffmpeg

        static_ffmpeg.add_paths()
    except Exception:
        pass
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


# ----------------------------------------------------------------- helpers
def _clean(text):
    return _ANSI_RE.sub("", str(text)).strip()


def friendly_error(error):
    """Traduce errores tecnicos de yt-dlp a mensajes claros en espanol."""
    raw = _clean(error)
    low = raw.lower()

    rules = [
        (("private video", "this video is private"),
         "El video es privado, no se puede descargar."),
        (("sign in to confirm your age", "age-restricted", "age restricted"),
         "El video tiene restriccion de edad y requiere iniciar sesion."),
        (("sign in to confirm you", "confirm you're not a bot", "login required"),
         "El sitio pide iniciar sesion o verificar que no sos un robot. "
         "Proba mas tarde o con otro enlace."),
        (("video unavailable", "this video is not available", "has been removed",
          "no longer available", "account associated with this video has been terminated"),
         "El video no esta disponible (fue eliminado o bloqueado)."),
        (("not available in your country", "geo restricted", "geo-restricted",
          "blocked it in your country"),
         "El video no esta disponible en tu pais."),
        (("unsupported url",),
         "Ese enlace no es compatible. Revisa que sea un enlace de un video o audio."),
        (("unable to download webpage", "getaddrinfo failed", "name or service not known",
          "temporary failure in name resolution", "network is unreachable",
          "timed out", "connection reset", "connection refused", "urlopen error",
          "failed to resolve"),
         "No hay conexion a internet (o el sitio no responde). "
         "Revisa tu conexion y volve a intentar."),
        (("http error 403", "forbidden"),
         "El sitio nego el acceso (error 403). Proba con el boton "
         "'Actualizar yt-dlp' y volve a intentar."),
        (("http error 429", "too many requests"),
         "Demasiados pedidos seguidos al sitio. Espera unos minutos."),
        (("requested format is not available",),
         "Esa calidad no esta disponible para este video. "
         "Proba con 'Mejor disponible'."),
        (("ffmpeg", "ffprobe"),
         "Fallo la conversion con FFmpeg. Ejecuta Instalar_Librerias.bat "
         "y volve a intentar."),
        (("permission denied", "access is denied"),
         "No hay permiso para guardar en esa carpeta. Elegi otra carpeta."),
        (("no space left",),
         "No queda espacio en el disco."),
    ]
    for needles, message in rules:
        if any(n in low for n in needles):
            return message

    short = raw.replace("ERROR:", "").strip()
    if len(short) > 300:
        short = short[:300] + "..."
    return (
        f"No se pudo completar la descarga:\n{short}\n\n"
        "Si el problema persiste, proba con 'Actualizar yt-dlp'."
    )


def parse_time(text):
    """Convierte 'ss', 'mm:ss' o 'hh:mm:ss' a segundos. Vacio -> None."""
    text = (text or "").strip()
    if not text:
        return None
    error = ValueError(
        f"Tiempo invalido: '{text}'. Usa segundos, mm:ss o hh:mm:ss (ej: 1:30)."
    )
    parts = text.split(":")
    if len(parts) > 3:
        raise error
    total = 0.0
    for part in parts:
        try:
            value = float(part)
        except ValueError:
            raise error from None
        if value < 0:
            raise error
        total = total * 60 + value
    return total


def fetch_playlist(url):
    """Lee una playlist sin descargar. Devuelve {'title', 'entries': [{'title','url'}]}.
    Si el enlace no es una playlist, 'entries' viene vacio."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "logger": _SilentLogger(),
        "extract_flat": "in_playlist",
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise RuntimeError(friendly_error(exc)) from exc

    entries = []
    for entry in (info or {}).get("entries") or []:
        if not entry:
            continue
        link = entry.get("url") or entry.get("webpage_url")
        if link and not str(link).startswith("http") and entry.get("id"):
            link = f"https://www.youtube.com/watch?v={entry['id']}"
        if not link:
            continue
        entries.append({"title": entry.get("title") or str(link), "url": str(link)})
    return {"title": (info or {}).get("title") or "Playlist", "entries": entries}


# ------------------------------------------------------------------ motor
class MediaDownloader:
    def __init__(self, progress_callback=None, status_callback=None):
        """
        progress_callback(percent, speed_bytes|None, eta_seconds|None, titulo|None)
        status_callback(texto)
        """
        self.progress_callback = progress_callback
        self.status_callback = status_callback
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def _status(self, text):
        if self.status_callback:
            self.status_callback(text)

    def _progress_hook(self, d):
        if self.cancel_event.is_set():
            raise DownloadCancelled()

        title = (d.get("info_dict") or {}).get("title")
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            percent = (done / total * 100) if total else 0.0
            if self.progress_callback:
                self.progress_callback(percent, d.get("speed"), d.get("eta"), title)
        elif status == "finished":
            self._status("Procesando archivo (conversion / union)...")
            if self.progress_callback:
                self.progress_callback(100.0, None, None, title)

    def _build_opts(self, mode, quality, out_dir, start, end, embed_thumbnail):
        opts = {
            "outtmpl": str(out_dir / "%(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "logger": _SilentLogger(),
            "progress_hooks": [self._progress_hook],
            "windowsfilenames": True,
        }

        if mode == "audio":
            bitrate = AUDIO_BITRATE_MAP.get(quality, "192")
            opts["format"] = "bestaudio/best"
            post = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": bitrate,
                },
                {"key": "FFmpegMetadata", "add_metadata": True},
            ]
            if embed_thumbnail:
                opts["writethumbnail"] = True
                post.insert(
                    0,
                    {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
                )
                post.append({"key": "EmbedThumbnail"})
            opts["postprocessors"] = post
        else:
            height = VIDEO_QUALITY_MAP.get(quality)
            if height:
                opts["format"] = (
                    f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
                    f"bestvideo[height<={height}]+bestaudio/"
                    f"best[height<={height}]/best"
                )
            else:
                opts["format"] = (
                    "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
                )
            opts["merge_output_format"] = "mp4"
            # Preferir H.264 + AAC: se reproduce en cualquier reproductor de
            # Windows sin instalar codecs extra (AV1/VP9 suelen dar problemas).
            opts["format_sort"] = ["vcodec:h264", "res", "acodec:m4a"]

        if start is not None or end is not None:
            opts["download_ranges"] = download_range_func(
                None, [(start or 0, end if end is not None else float("inf"))]
            )
            opts["force_keyframes_at_cuts"] = True

        return opts

    def download(self, url, mode, quality, out_dir, start=None, end=None,
                 embed_thumbnail=True):
        """Descarga `url`. mode: 'audio' o 'video'. Devuelve el titulo.

        start / end: segundos (o None) para recortar el fragmento.
        """
        if start is not None and end is not None and end <= start:
            raise ValueError("El tiempo 'Hasta' debe ser mayor que 'Desde'.")

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        self._status("Preparando FFmpeg (la primera vez puede tardar)...")
        if not ensure_ffmpeg_available():
            raise RuntimeError(
                "No se pudo preparar FFmpeg. Revisa tu conexion a internet "
                "y volve a intentar (la primera vez se descarga automaticamente)."
            )

        # Si falla con portada, se reintenta una vez sin portada.
        attempts = [True, False] if (mode == "audio" and embed_thumbnail) else [False]

        self._status("Analizando enlace...")
        info = None
        last_error = None
        for use_thumbnail in attempts:
            opts = self._build_opts(mode, quality, out_dir, start, end, use_thumbnail)
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                break
            except DownloadCancelled:
                raise
            except Exception as exc:
                if self.cancel_event.is_set():
                    raise DownloadCancelled() from exc
                last_error = exc
        else:
            raise RuntimeError(friendly_error(last_error)) from last_error

        if self.cancel_event.is_set():
            raise DownloadCancelled()

        return (info or {}).get("title") or "Descarga completada"
