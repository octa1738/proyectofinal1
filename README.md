# Media Downloader

App de escritorio para Windows que descarga **video (MP4)** o **audio (MP3)** desde un enlace
(YouTube, SoundCloud, TikTok, Vimeo, X/Twitter y cientos de sitios mas).

Hecha en Python con CustomTkinter + yt-dlp + FFmpeg.

## Funciones

- Descarga de audio MP3 (320/256/192/128 kbps) o video MP4 (hasta 1080p o mejor disponible).
- Video en H.264 + AAC: se abre en cualquier reproductor de Windows.
- **Cola de enlaces:** pega varios enlaces (uno por linea) y se descargan uno tras otro.
- **Playlists:** boton "Playlist..." para elegir que videos bajar.
- **Portada incrustada** en el MP3 (opcional).
- **Recorte** del fragmento que quieras (desde / hasta, ej. `1:30`).
- Barra de progreso con velocidad, tiempo restante y titulo del video.
- Boton para cancelar sin cerrar la app.
- Historial y preferencias guardados (carpeta, formato, calidad, tema).
- Tema oscuro, claro o del sistema.
- Mensajes de error claros y boton "Actualizar yt-dlp".
- Se pega solo el enlace si lo tenes copiado al abrir la app.

## Instalacion y uso

1. Instala Python 3.10 o superior desde python.org (marca "Add python.exe to PATH").
2. Doble clic en `Instalar_Librerias.bat` (instala las librerias y descarga FFmpeg).
3. Abre la app con `iniciar_app.bat`.
4. Opcional: `Crear_Acceso_Directo.bat` crea un acceso directo en el escritorio.
   (No copies `iniciar_app.bat` solo: depende de los otros archivos de la carpeta.)

Por terminal: `pip install -r requirements.txt` y luego `python app.py`.

## Crear el .exe

Doble clic en `Crear_Exe.bat`. El programa queda en `dist/MediaDownloader/`
(lleva la carpeta completa, no solo el .exe).

## Archivos

| Archivo | Funcion |
|---|---|
| `app.py` | Interfaz grafica (frontend) |
| `downloader.py` | Motor de descarga y conversion (backend) |
| `requirements.txt` | Librerias necesarias |
| `Instalar_Librerias.bat` | Instala librerias y FFmpeg |
| `iniciar_app.bat` | Abre la app sin consola |
| `Crear_Acceso_Directo.bat` | Acceso directo en el escritorio |
| `build_exe.py` / `Crear_Exe.bat` | Generan el .exe con PyInstaller |

## Aviso

Usa esta herramienta solo para contenido que tengas derecho a descargar y respeta
los terminos de cada sitio.
