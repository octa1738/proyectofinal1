"""Interfaz grafica (frontend) del Media Downloader, hecha con CustomTkinter."""

import ctypes
import json
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from downloader import (
    AUDIO_BITRATE_MAP,
    VIDEO_QUALITY_MAP,
    DownloadCancelled,
    MediaDownloader,
    fetch_playlist,
    parse_time,
)

MODE_AUDIO = "Audio (MP3)"
MODE_VIDEO = "Video (MP4)"

THEMES = {"Oscuro": "dark", "Claro": "light", "Sistema": "system"}

# Preferencias e historial se guardan en la carpeta del usuario, asi
# funcionan aunque muevas o copies la app.
CONFIG_DIR = Path.home() / ".media_downloader"
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "history.json"
HISTORY_LIMIT = 100

DEFAULT_CONFIG = {
    "mode": MODE_AUDIO,
    "audio_quality": "192 kbps",
    "video_quality": "1080p (Full HD)",
    "folder": "",
    "theme": "Oscuro",
    "thumbnail": True,
}


def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _format_speed(bps):
    if not bps:
        return "-"
    if bps >= 1024 * 1024:
        return f"{bps / (1024 * 1024):.1f} MB/s"
    return f"{bps / 1024:.0f} KB/s"


def _format_eta(seconds):
    if seconds is None:
        return "-"
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _shorten(text, limit):
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


# --------------------------------------------------- dialogo de playlists
class PlaylistDialog(ctk.CTkToplevel):
    MAX_SHOWN = 300

    def __init__(self, parent, title, entries, on_accept):
        super().__init__(parent)
        self.title("Elegir de la playlist")
        self.geometry("580x560")
        self.transient(parent)
        self._on_accept = on_accept
        self._items = []

        ctk.CTkLabel(
            self, text=_shorten(title, 80), font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(16, 2), padx=16)

        total = len(entries)
        note = f"{total} videos"
        if total > self.MAX_SHOWN:
            note += f" (se muestran los primeros {self.MAX_SHOWN})"
        ctk.CTkLabel(self, text=note, text_color="gray60").pack(pady=(0, 8))

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16)
        ctk.CTkButton(
            top, text="Seleccionar todo", width=130, command=lambda: self._set_all(True)
        ).pack(side="left")
        ctk.CTkButton(
            top, text="Ninguno", width=90, fg_color="gray30", hover_color="gray40",
            command=lambda: self._set_all(False),
        ).pack(side="left", padx=8)

        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True, padx=16, pady=10)
        for entry in entries[: self.MAX_SHOWN]:
            var = ctk.BooleanVar(value=True)
            ctk.CTkCheckBox(scroll, text=_shorten(entry["title"], 70), variable=var).pack(
                anchor="w", pady=3
            )
            self._items.append((var, entry["url"]))

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=16, pady=(0, 16))
        ctk.CTkButton(
            bottom, text="Agregar seleccionados a la cola", height=38, command=self._accept
        ).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            bottom, text="Cancelar", height=38, width=100, fg_color="gray30",
            hover_color="gray40", command=self.destroy,
        ).pack(side="left", padx=(8, 0))

        self.after(150, self._grab)

    def _grab(self):
        try:
            self.grab_set()
            self.focus()
        except Exception:
            pass

    def _set_all(self, value):
        for var, _ in self._items:
            var.set(value)

    def _accept(self):
        urls = [url for var, url in self._items if var.get()]
        self.destroy()
        if urls:
            self._on_accept(urls)


# ------------------------------------------------------- ventana principal
class MediaDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.cfg = dict(DEFAULT_CONFIG)
        loaded = _load_json(CONFIG_FILE, {})
        if isinstance(loaded, dict):
            self.cfg.update({k: v for k, v in loaded.items() if k in DEFAULT_CONFIG})
        self._sanitize_config()
        ctk.set_appearance_mode(THEMES[self.cfg["theme"]])
        ctk.set_default_color_theme("blue")

        history = _load_json(HISTORY_FILE, [])
        self.history_items = history if isinstance(history, list) else []

        self.title("Media Downloader")
        self.geometry("700x780")
        self.minsize(620, 640)

        folder = Path(self.cfg["folder"]) if self.cfg["folder"] else None
        if not folder or not folder.exists():
            downloads = Path.home() / "Downloads"
            folder = downloads if downloads.exists() else Path.home()
        self.output_dir = folder

        self.downloader = None
        self.worker = None
        self._cur = (0, 1)  # (indice actual, total) de la cola

        self._build_ui()
        self._refresh_history()
        self._auto_paste_clipboard()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _sanitize_config(self):
        cfg = self.cfg
        if cfg["mode"] not in (MODE_AUDIO, MODE_VIDEO):
            cfg["mode"] = MODE_AUDIO
        if cfg["audio_quality"] not in AUDIO_BITRATE_MAP:
            cfg["audio_quality"] = DEFAULT_CONFIG["audio_quality"]
        if cfg["video_quality"] not in VIDEO_QUALITY_MAP:
            cfg["video_quality"] = DEFAULT_CONFIG["video_quality"]
        if cfg["theme"] not in THEMES:
            cfg["theme"] = "Oscuro"
        cfg["thumbnail"] = bool(cfg["thumbnail"])
        if not isinstance(cfg["folder"], str):
            cfg["folder"] = ""

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=8)
        pad = {"padx": 16}

        # Encabezado + tema
        header = ctk.CTkFrame(body, fg_color="transparent")
        header.pack(fill="x", pady=(8, 0), **pad)
        ctk.CTkLabel(
            header, text="Media Downloader", font=ctk.CTkFont(size=26, weight="bold")
        ).pack(side="left")
        self.theme_menu = ctk.CTkOptionMenu(
            header, values=list(THEMES), width=100, command=self._on_theme_change
        )
        self.theme_menu.set(self.cfg["theme"])
        self.theme_menu.pack(side="right")
        ctk.CTkLabel(header, text="Tema:", text_color="gray60").pack(side="right", padx=6)

        ctk.CTkLabel(
            body,
            text="Descarga video (MP4) o audio (MP3) desde uno o varios enlaces",
            text_color="gray60", anchor="w",
        ).pack(fill="x", pady=(0, 14), **pad)

        # Enlaces (uno por linea = cola)
        ctk.CTkLabel(
            body, text="Enlaces (uno por linea):", anchor="w"
        ).pack(fill="x", **pad)
        link_row = ctk.CTkFrame(body, fg_color="transparent")
        link_row.pack(fill="x", pady=(4, 0), **pad)
        self.url_box = ctk.CTkTextbox(link_row, height=88)
        self.url_box.pack(side="left", fill="both", expand=True)
        side = ctk.CTkFrame(link_row, fg_color="transparent")
        side.pack(side="left", padx=(8, 0))
        ctk.CTkButton(side, text="Pegar", width=110, command=self._paste).pack()
        ctk.CTkButton(
            side, text="Limpiar", width=110, fg_color="gray30", hover_color="gray40",
            command=self._clear,
        ).pack(pady=6)
        self.playlist_btn = ctk.CTkButton(
            side, text="Playlist...", width=110, command=self._open_playlist
        )
        self.playlist_btn.pack()

        # Formato
        self.mode_var = ctk.StringVar(value=self.cfg["mode"])
        ctk.CTkSegmentedButton(
            body, values=[MODE_AUDIO, MODE_VIDEO], variable=self.mode_var,
            command=self._on_mode_change, height=36,
        ).pack(fill="x", pady=(16, 10), **pad)

        # Calidad + portada
        quality_row = ctk.CTkFrame(body, fg_color="transparent")
        quality_row.pack(fill="x", **pad)
        self.quality_label = ctk.CTkLabel(quality_row, text="")
        self.quality_label.pack(side="left")
        self.quality_menu = ctk.CTkOptionMenu(
            quality_row, values=[""], command=self._on_quality_change
        )
        self.quality_menu.pack(side="left", padx=(12, 0))
        self.thumb_var = ctk.BooleanVar(value=self.cfg["thumbnail"])
        self.thumb_check = ctk.CTkCheckBox(
            quality_row, text="Incrustar portada en el MP3", variable=self.thumb_var
        )
        self.thumb_check.pack(side="right")
        self._apply_mode_options()

        # Recorte
        trim_row = ctk.CTkFrame(body, fg_color="transparent")
        trim_row.pack(fill="x", pady=(14, 0), **pad)
        ctk.CTkLabel(trim_row, text="Recortar (opcional):").pack(side="left")
        ctk.CTkLabel(trim_row, text="Desde", text_color="gray60").pack(side="left", padx=(12, 4))
        self.trim_start = ctk.CTkEntry(trim_row, width=80, placeholder_text="00:30")
        self.trim_start.pack(side="left")
        ctk.CTkLabel(trim_row, text="Hasta", text_color="gray60").pack(side="left", padx=(12, 4))
        self.trim_end = ctk.CTkEntry(trim_row, width=80, placeholder_text="02:15")
        self.trim_end.pack(side="left")

        # Carpeta de destino
        folder_row = ctk.CTkFrame(body, fg_color="transparent")
        folder_row.pack(fill="x", pady=(14, 0), **pad)
        ctk.CTkLabel(folder_row, text="Guardar en:").pack(side="left")
        self.folder_label = ctk.CTkLabel(
            folder_row, text=_shorten(str(self.output_dir), 48), text_color="gray60", anchor="w"
        )
        self.folder_label.pack(side="left", fill="x", expand=True, padx=10)
        ctk.CTkButton(
            folder_row, text="Elegir carpeta", width=110, command=self._choose_folder
        ).pack(side="right")

        # Botones principales
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(20, 10), **pad)
        self.download_btn = ctk.CTkButton(
            btn_row, text="Descargar ahora", height=44,
            font=ctk.CTkFont(size=15, weight="bold"), command=self._start_download,
        )
        self.download_btn.pack(side="left", fill="x", expand=True)
        self.cancel_btn = ctk.CTkButton(
            btn_row, text="Cancelar descarga", height=44, state="disabled",
            fg_color="#8b2e2e", hover_color="#a33a3a", command=self._cancel_download,
        )
        self.cancel_btn.pack(side="left", fill="x", expand=True, padx=(10, 0))

        # Progreso
        self.progress = ctk.CTkProgressBar(body, height=14)
        self.progress.set(0)
        self.progress.pack(fill="x", **pad)
        self.status_label = ctk.CTkLabel(
            body, text="Listo.", text_color="gray60", wraplength=620, justify="left"
        )
        self.status_label.pack(pady=(6, 0), **pad)

        tools = ctk.CTkFrame(body, fg_color="transparent")
        tools.pack(fill="x", pady=(10, 8), **pad)
        ctk.CTkButton(
            tools, text="Abrir carpeta de descargas", fg_color="gray30",
            hover_color="gray40", command=self._open_folder,
        ).pack(side="left", fill="x", expand=True)
        self.update_btn = ctk.CTkButton(
            tools, text="Actualizar yt-dlp", fg_color="gray30", hover_color="gray40",
            command=self._update_ytdlp,
        )
        self.update_btn.pack(side="left", fill="x", expand=True, padx=(10, 0))

        # Historial
        hist_head = ctk.CTkFrame(body, fg_color="transparent")
        hist_head.pack(fill="x", **pad)
        ctk.CTkLabel(hist_head, text="Historial", anchor="w").pack(side="left")
        ctk.CTkButton(
            hist_head, text="Borrar historial", width=120, height=26, fg_color="gray30",
            hover_color="gray40", command=self._clear_history,
        ).pack(side="right")
        self.history = ctk.CTkTextbox(body, height=170)
        self.history.pack(fill="both", expand=True, pady=(4, 12), **pad)
        self.history.configure(state="disabled")

    # ------------------------------------------------------ preferencias
    def _save_config(self):
        self.cfg["mode"] = self.mode_var.get()
        self.cfg["folder"] = str(self.output_dir)
        self.cfg["thumbnail"] = bool(self.thumb_var.get())
        _save_json(CONFIG_FILE, self.cfg)

    def _on_close(self):
        self._save_config()
        self.destroy()

    def _on_theme_change(self, value):
        self.cfg["theme"] = value
        ctk.set_appearance_mode(THEMES[value])
        self._save_config()

    def _apply_mode_options(self):
        if self.mode_var.get() == MODE_AUDIO:
            self.quality_label.configure(text="Calidad de audio:")
            self.quality_menu.configure(values=list(AUDIO_BITRATE_MAP))
            self.quality_menu.set(self.cfg["audio_quality"])
            self.thumb_check.configure(state="normal")
        else:
            self.quality_label.configure(text="Resolucion maxima:")
            self.quality_menu.configure(values=list(VIDEO_QUALITY_MAP))
            self.quality_menu.set(self.cfg["video_quality"])
            self.thumb_check.configure(state="disabled")

    def _on_mode_change(self, _value):
        self._apply_mode_options()
        self._save_config()

    def _on_quality_change(self, value):
        key = "audio_quality" if self.mode_var.get() == MODE_AUDIO else "video_quality"
        self.cfg[key] = value
        self._save_config()

    # ------------------------------------------------------------ enlaces
    def _get_urls(self):
        seen, urls = set(), []
        for line in self.url_box.get("1.0", "end").splitlines():
            line = line.strip()
            if line and line not in seen:
                seen.add(line)
                urls.append(line)
        return urls

    def _set_urls(self, urls):
        self.url_box.delete("1.0", "end")
        self.url_box.insert("1.0", "\n".join(urls))
        self._set_status(f"{len(urls)} enlaces en la cola.")

    def _clipboard_url(self):
        try:
            text = self.clipboard_get().strip()
        except Exception:
            return ""
        return text if text.lower().startswith(("http://", "https://")) else ""

    def _auto_paste_clipboard(self):
        url = self._clipboard_url()
        if url and "\n" not in url:
            self.url_box.insert("1.0", url)

    def _paste(self):
        try:
            text = self.clipboard_get().strip()
        except Exception:
            return
        if not text:
            return
        current = self.url_box.get("1.0", "end").strip()
        if current:
            self.url_box.insert("end", ("" if current.endswith("\n") else "\n") + text)
        else:
            self.url_box.insert("1.0", text)

    def _clear(self):
        self.url_box.delete("1.0", "end")

    # ---------------------------------------------------------- playlists
    def _open_playlist(self):
        urls = self._get_urls()
        if not urls:
            messagebox.showwarning(
                "Falta el enlace", "Pega primero el enlace de la playlist."
            )
            return
        self.playlist_btn.configure(state="disabled")
        self._set_status("Leyendo playlist...")
        threading.Thread(target=self._playlist_worker, args=(urls[0],), daemon=True).start()

    def _playlist_worker(self, url):
        try:
            info = fetch_playlist(url)
        except Exception as exc:
            self.after(0, self._playlist_error, str(exc))
            return
        self.after(0, self._playlist_ready, info)

    def _playlist_error(self, message):
        self.playlist_btn.configure(state="normal")
        self._set_status("No se pudo leer la playlist.")
        messagebox.showerror("Error", message)

    def _playlist_ready(self, info):
        self.playlist_btn.configure(state="normal")
        self._set_status("Listo.")
        if not info["entries"]:
            messagebox.showinfo(
                "Sin playlist",
                "Ese enlace no es una playlist (o esta vacia). "
                "Se descargara como un video individual.",
            )
            return
        PlaylistDialog(self, info["title"], info["entries"], self._set_urls)

    # -------------------------------------------------------------- otros
    def _choose_folder(self):
        chosen = filedialog.askdirectory(initialdir=str(self.output_dir))
        if chosen:
            self.output_dir = Path(chosen)
            self.folder_label.configure(text=_shorten(str(self.output_dir), 48))
            self._save_config()

    def _open_folder(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(self.output_dir)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self.output_dir)])
            else:
                subprocess.Popen(["xdg-open", str(self.output_dir)])
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo abrir la carpeta:\n{exc}")

    def _update_ytdlp(self):
        if getattr(sys, "frozen", False):
            messagebox.showinfo(
                "Actualizar yt-dlp",
                "Esta version es un .exe y no se puede actualizar desde aca.\n"
                "Genera el .exe de nuevo (Crear_Exe.bat) para incluir la ultima version.",
            )
            return
        self.update_btn.configure(state="disabled")
        self._set_status("Actualizando yt-dlp (puede tardar un minuto)...")
        threading.Thread(target=self._update_worker, daemon=True).start()

    def _update_worker(self):
        flags = 0x08000000 if sys.platform.startswith("win") else 0  # CREATE_NO_WINDOW
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                capture_output=True, text=True, timeout=300,
                stdin=subprocess.DEVNULL, creationflags=flags,
            )
            ok = result.returncode == 0
            detail = (result.stderr or result.stdout or "").strip()[-300:]
        except Exception as exc:
            ok, detail = False, str(exc)
        self.after(0, self._update_done, ok, detail)

    def _update_done(self, ok, detail):
        self.update_btn.configure(state="normal")
        if ok:
            self._set_status("yt-dlp actualizado. Cerra y volve a abrir la app.")
            messagebox.showinfo(
                "Actualizar yt-dlp",
                "yt-dlp se actualizo correctamente.\n"
                "Cerra la app y abrila de nuevo para usar la nueva version.",
            )
        else:
            self._set_status("No se pudo actualizar yt-dlp.")
            messagebox.showerror(
                "Actualizar yt-dlp",
                "No se pudo actualizar. Revisa tu conexion a internet.\n\n" + detail,
            )

    # ------------------------------------------------------------ descarga
    def _start_download(self):
        urls = self._get_urls()
        if not urls:
            messagebox.showwarning("Falta el enlace", "Pega primero al menos un enlace.")
            return
        bad = [u for u in urls if not u.lower().startswith(("http://", "https://"))]
        if bad:
            messagebox.showwarning(
                "Enlace invalido",
                "Todos los enlaces deben empezar con http:// o https://\n\n"
                f"Revisa: {_shorten(bad[0], 80)}",
            )
            return

        try:
            start = parse_time(self.trim_start.get())
            end = parse_time(self.trim_end.get())
            if start is not None and end is not None and end <= start:
                raise ValueError("El tiempo 'Hasta' debe ser mayor que 'Desde'.")
        except ValueError as exc:
            messagebox.showwarning("Recorte invalido", str(exc))
            return

        mode = "audio" if self.mode_var.get() == MODE_AUDIO else "video"
        quality = self.quality_menu.get()
        thumbnail = bool(self.thumb_var.get())
        self._save_config()

        self.download_btn.configure(state="disabled")
        self.playlist_btn.configure(state="disabled")
        self.update_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress.set(0)
        self._cur = (0, len(urls))
        self._set_status("Iniciando...")

        self.downloader = MediaDownloader(
            progress_callback=self._progress_from_thread,
            status_callback=self._status_from_thread,
        )
        self.worker = threading.Thread(
            target=self._worker,
            args=(urls, mode, quality, self.output_dir, start, end, thumbnail),
            daemon=True,
        )
        self.worker.start()

    def _cancel_download(self):
        if self.downloader:
            self.downloader.cancel()
            self._set_status("Cancelando...")
            self.cancel_btn.configure(state="disabled")

    # ------------------------------------------------- hilo secundario
    def _worker(self, urls, mode, quality, out_dir, start, end, thumbnail):
        total = len(urls)
        done, failed, cancelled = 0, [], False
        for index, url in enumerate(urls):
            if self.downloader.cancel_event.is_set():
                cancelled = True
                break
            self._cur = (index, total)
            try:
                title = self.downloader.download(
                    url, mode, quality, out_dir, start, end, thumbnail
                )
                done += 1
                self.after(0, self._on_item_done, title, mode, index, total)
            except DownloadCancelled:
                cancelled = True
                break
            except Exception as exc:
                failed.append((url, str(exc) or "Error desconocido."))
        self.after(0, self._on_finished, done, total, failed, cancelled)

    def _status_from_thread(self, text):
        index, total = self._cur
        prefix = f"[{index + 1}/{total}] " if total > 1 else ""
        self.after(0, self._set_status, prefix + text)

    def _progress_from_thread(self, percent, speed, eta, title):
        index, total = self._cur
        self.after(0, self._update_progress, index, total, percent, speed, eta, title)

    # -------------------------------------------- actualizacion de la GUI
    def _set_status(self, text):
        self.status_label.configure(text=text)

    def _update_progress(self, index, total, percent, speed, eta, title):
        overall = (index + max(0.0, min(100.0, percent)) / 100) / total
        self.progress.set(max(0.0, min(1.0, overall)))
        if speed is not None or eta is not None:
            prefix = f"[{index + 1}/{total}] " if total > 1 else ""
            name = f"{_shorten(title, 45)}  -  " if title else ""
            self._set_status(
                f"{prefix}{name}{percent:.0f}%  |  {_format_speed(speed)}  |  "
                f"Restante: {_format_eta(eta)}"
            )

    def _reset_buttons(self):
        self.download_btn.configure(state="normal")
        self.playlist_btn.configure(state="normal")
        self.update_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")

    def _on_item_done(self, title, mode, index, total):
        self.progress.set((index + 1) / total)
        tipo = "MP3" if mode == "audio" else "MP4"
        self.history_items.insert(
            0,
            {"fecha": datetime.now().strftime("%d/%m %H:%M"), "tipo": tipo, "titulo": title},
        )
        del self.history_items[HISTORY_LIMIT:]
        _save_json(HISTORY_FILE, self.history_items)
        self._refresh_history()

    def _on_finished(self, done, total, failed, cancelled):
        self._reset_buttons()
        if cancelled:
            self.progress.set(0)
            self._set_status(f"Descarga cancelada ({done} de {total} completadas).")
            return
        if failed:
            self._set_status(f"Terminado con errores: {done} de {total} completadas.")
            lines = [f"- {_shorten(url, 60)}\n  {msg}" for url, msg in failed[:5]]
            extra = f"\n\n(y {len(failed) - 5} mas)" if len(failed) > 5 else ""
            messagebox.showerror(
                "Algunas descargas fallaron", "\n\n".join(lines) + extra
            )
            return
        self.progress.set(1)
        self._set_status(
            "Descarga completada." if total == 1 else f"Cola completada: {done} descargas."
        )

    # ----------------------------------------------------------- historial
    def _refresh_history(self):
        self.history.configure(state="normal")
        self.history.delete("1.0", "end")
        lines = []
        for item in self.history_items:
            if isinstance(item, dict):
                lines.append(
                    f"{item.get('fecha', '')}  [{item.get('tipo', '')}]  {item.get('titulo', '')}"
                )
        self.history.insert("1.0", "\n".join(lines))
        self.history.configure(state="disabled")

    def _clear_history(self):
        if not self.history_items:
            return
        if messagebox.askyesno("Borrar historial", "¿Borrar todo el historial?"):
            self.history_items = []
            _save_json(HISTORY_FILE, self.history_items)
            self._refresh_history()


def _set_windows_app_id():
    if sys.platform.startswith("win"):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "mediadownloader.app"
            )
        except Exception:
            pass


if __name__ == "__main__":
    _set_windows_app_id()
    app = MediaDownloaderApp()
    app.mainloop()
