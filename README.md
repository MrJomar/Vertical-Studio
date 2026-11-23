# Vertical Studio

Genera videos verticales 1080×1920 **100 % en tu PC** (Windows): mapas animados, B-roll con voz y
subtítulos, y clips de videos largos. Codifica con **NVENC** (GPU NVIDIA) si está disponible; si no, con x264.

## Instalar (Windows)
1. Python 3.10+ (marca *Add to PATH*) y FFmpeg (`winget install Gyan.FFmpeg`, o copia `ffmpeg.exe`/`ffprobe.exe` a `bin\`).
2. Doble clic en `instalar.bat`. 3. Abre con `iniciar.bat` (o `python app.py`).

## Tipos de escena
| Tipo | Qué hace |
|---|---|
| `map` | **Mapa real** (satélite, oscuro, claro, calles, terreno; teselas descargadas y cacheadas; sin internet cae a vectorial): `zoom` (vuela a países), `tour` (visita lugares), `route` (ruta animada). Acepta tu propio **GeoJSON** (barrios, colonias, estados) |
| `vector` | **Animación vectorial por capas** (estilo explicativo): 24 elementos dibujados por código (personajes, bacterias, medidor, puerta, pez, gato, personas…), 9 fondos animados, animaciones (pop, float, drift, drop…) sincronizadas con palabras de la narración. Se pueden generar con IA (Gemini gratis) desde un guion |
| `broll` | Imágenes/videos con fundido cruzado + narración + subtítulos palabra por palabra |
| `clip` | Recorta un video largo a 9:16 (`blur` fondo difuminado, `cover` recorte, `face` sigue el rostro) con subtítulos y gancho |

Cualquier escena con `narration` genera voz y subtítulos, y su duración se ajusta sola al audio.

## Uso rápido
La app abre una ventana propia (Edge/Chrome en modo aplicación). Arriba: **✨ Ejemplos** muestra cómo queda cada tipo de video y
permite usarlo como base. Izquierda: escenas. Centro: vista previa con reproducción. Derecha: propiedades.
- **Guion → escenas**: pega un guion completo (lo divide en escenas de B-roll por frases) y opcionalmente una carpeta de imágenes, que empareja por nombre de archivo o en orden.
- **Plantillas**: en Ajustes guarda tus ajustes por canal (Randompedia, Xolo Explorador…) y aplícalos con un clic.
- **Auto-clips**: elige un video largo y propone los mejores momentos como escenas `clip`.
- **Exportar video**: 1080×1920 con barra de progreso. Ctrl+S guarda el proyecto.

### Elementos sobre el mapa
Campo **overlays** (JSON): íconos, cifras o fotos ancladas a un lugar o coordenada y sincronizadas con una palabra de la narración:
`{"asset":"etiqueta","place":"Madrid","text":"28 años","at":"años","w":0.3}` · `{"photo":"cara.jpg","lat":51.5,"lon":-0.12,"shape":"hexagono"}`.
En *Lugares* también puedes escribir `Nombre | lat, lon | foto.jpg` para un pin con foto.

### Mapas reales
Estilos: satélite (Esri World Imagery), oscuro/claro (CARTO), calles (OpenStreetMap), terreno (Esri). Las teselas se guardan en `cache/tiles`.
Respeta los términos de cada proveedor (la atribución se dibuja en el video). Para uso comercial intensivo pon tu propio
proveedor en Ajustes → *URL de teselas propia* (`https://…/{z}/{x}/{y}.png`).

Línea de comandos: `python cli.py render examples/demo_mapas.json -o demo.mp4`
(también `preview`, `top`, `autoclip`; ver `python cli.py -h`).

## Formato del proyecto (JSON)
Mira `examples/*.json`. Las rutas relativas se buscan junto al archivo del proyecto.
`settings` admite: `theme` (neon, oscuro, retro, papel, esmeralda), `tts_engine` (`edge`, `sapi`, `silencio`), `voice`,
`music`, `music_volume`, `transition` (fade, slide, zoom, flash, wipe, cut), `watermark`, `encoder`, `quality`, etc.

## Notas
- Voz `edge` y la geolocalización de `places` sin lat/lon necesitan internet; `sapi` (Windows) y `silencio` no.
- La primera transcripción con Whisper descarga el modelo. Con GPU NVIDIA usa CUDA automáticamente.
- El render de cuadros corre en Python (CPU); NVENC acelera solo la codificación final.
- Fuentes: usa Anton/Montserrat si las pones en `fonts\`; si no, Impact/Arial/Segoe del sistema.
- Datos de mapas: Natural Earth (dominio público) vía world-atlas.

## Actualizaciones

Al iniciar, el programa compara su versión (`vstudio/__init__.py`) con la de GitHub y, si hay una nueva, muestra un aviso con botón para abrir el repositorio (allí: Code → Download ZIP, o `git pull`).
Se configura en **Ajustes → Actualizaciones** (activar/desactivar, repositorio, token).

Como el repositorio es **privado**, hace falta un token de solo lectura:
GitHub → Settings → Developer settings → Fine-grained tokens → *Generate new token* → Repository access: solo `Vertical-Studio` → Permissions: **Contents: Read-only**. Pégalo en Ajustes. Se guarda solo en tu PC (`cache/config.json`, ignorado por git).
Para publicar una versión nueva, sube `__version__` en `vstudio/__init__.py`.
