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

### Mapas estilo documental (v2.1)
Una escena de mapa en modo `route` admite (ver el ejemplo «Mapa: expedición estilo documental»):
- `route_color`, `route_width`: línea gruesa (p. ej. `#f2ff2e`, 11). `follow: true`: la cámara sigue la punta; `follow_zoom`: cuánto se acerca.
- `tip_photo`, `tip_name`: avatar hexagonal con nombre que viaja en la punta.
- `route_labels`: `[{"frac":0.3,"text":"2 años"}, {"frac":0.8,"text":"28 años","style":"etiqueta"}]` rótulos pegados a la ruta.
- `arrows`: `[{"from":"Lima","to":[53.7,-0.3],"label":"Hull, UK","at":"palabra","dur":1.6}]` flechas punteadas en arco.
- `highlight`: `"Colombia:#2a7bff, Kazajistán:#e02020"` países con color propio (`hl_alpha` = opacidad).
- `tilt` (0-40): inclinación 3D aproximada · `fx`: `nieve`, `polvo_luz`, `bokeh` · `intro`: `blanco`/`negro` · `grade`: `vivo`/`cine` (más color).
- Estilo de mapa **natural** (NASA, relieve y fondo marino, uso libre): zoom máximo moderado; buena opción para vista continental.

### Animación vectorial: efectos (v2.1)
- Escena: `fx` = `humo, bokeh, bokeh_frente, corazones, brillos, nieve, burbujas, polvo_luz`; cámara `drift`/`push_fuerte`; `caption_style: "suave"` (por defecto).
- Capa: `blur` (profundidad de campo), `glow` (aura), `rot_var` (ángulos variados),
  `shape` = `cara|corazon|circulo|estrella|texto:HOLA` con `count`, `form` (palabra) y `form_dur`: el enjambre forma la figura;
  `react` + `rfrom` + `rdist` + `react_mood` + `react_shrink` + `react_fade`: los personajes reaccionan al impacto.
- Nuevos elementos: `molecula`, `burbuja_villano`, `luz`, `humo`.

### Voces, Gemini y perfiles (v2.3)
Botón **🎙 Voces**: motor (Edge, **Gemini**, voces locales de Windows o sin voz), lista de voces con buscador, botón **Probar voz**, modelo de audio de Gemini (solo modelos TTS; con tu API key se lee la lista real de tu cuenta), estilo/tono y velocidad.
- **API key de Gemini**: se guarda solo en tu PC (`cache/voices.json`), nunca dentro de los proyectos.
- **Perfiles**: guarda una combinación (motor + voz + modelo + estilo + velocidad) con un nombre y úsala en un proyecto (`"voice_profile": "Narrador serio"` en los ajustes del proyecto o de una escena) o como **perfil por defecto de cada tipo de video** (mapa, vectores, B-roll, clip).
- Orden de prioridad por escena: perfil de la escena › voz de la escena › perfil del proyecto › perfil del tipo › ajustes del proyecto. «Sin voz» en el proyecto apaga todo (vista previa y proyectos mudos).
- Al **abrir un proyecto .json** con narraciones aparece un selector de motor y perfil.
- **Inicio**: panel con trabajos en curso (progreso, cancelar), terminados y proyectos recientes.
- Los tiempos por palabra de Gemini son estimados (el servicio no los entrega); Edge sí da tiempos exactos.

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


## Estilos de guion (v2.4)
La carpeta `estilos/` guarda lo aprendido de los videos de referencia (estructura, ritmo, recursos) como `.json` (el programa lo usa) y `.md` (guía con ejemplo). En *Animación con IA* eliges un estilo: se añade al prompt de escenas y puedes copiar el **prompt para escribir el guion** en ese estilo. Estilos propios privados: `cache/estilos_privados/*.json` (el actualizador no los toca).

## Voz maestra (v2.4.2)
Con Gemini, todo el guion se envía en **una sola llamada** y el audio se corta por escenas en las pausas más cercanas al punto donde termina cada una: misma entonación y ritmo en todo el video, y menos peticiones. Cada audio se valida (existe, tiene voz, duración coherente) y se reintenta hasta 3 veces. Se desactiva con `"master_audio": false` en los ajustes del proyecto. El estilo de voz de una palabra («Alegre») ahora se envía como orden completa («Di de forma alegre:») para que no se lea en voz alta.
