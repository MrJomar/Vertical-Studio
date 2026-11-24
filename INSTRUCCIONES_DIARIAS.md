# Instrucciones de la tarea diaria — Vertical Studio

Cada corrida deja **4 proyectos de video vertical** listos para que Omar los abra en el programa, los renderice con la voz de su PC y los revise. Debe terminar antes de las 5:00 am (hora de Ciudad de México). Trabaja sola: si algo falla, deja lo que sí quedó bien y anótalo en `proyectos_diarios/AAAA-MM-DD/NOTAS.md`.

## 1. Preparación
1. Repositorio: `MrJomar/Vertical-Studio`, rama `main`. Clónalo y trabaja en la carpeta del repo.
2. Lee `proyectos_diarios/_temas_usados.md` (historial de temas y su familia) y los JSON de `proyectos_ejemplo/prueba_miel.json` y `proyectos_ejemplo/prueba_piel_de_gallina.json` como referencia de formato y calidad.
3. Lista los assets disponibles: `python3 -c "import vstudio.project; from vstudio.vector_assets import ASSETS; [print(k, v[2], '|', v[3]) for k, v in ASSETS.items()]"` (importa `vstudio.project` primero).

## 2. Elegir 4 temas
- **Familias:** cuerpo humano, cocina y comida, naturaleza y animales, historia y objetos cotidianos, tecnología y nostalgia (consolas, VHS, cassettes, juguetes), lugares y espacio, hábitos y mitos de la vida diaria.
- Los 4 del día deben ser de **4 familias distintas**, y ninguno de la misma familia que los últimos 3 videos del historial.
- No repitas temas del historial. No uses mapas, fotos reales ni nada que dependa de internet o de archivos que no estén en el repo.
- **Filtro de calidad** (descarta el tema si falla alguno):
  1. Tiene un gancho concreto en la primera frase (promesa o tensión, no "hoy hablaremos de…").
  2. Tiene un giro verificable: una idea común que se rompe o un dato inesperado.
  3. Cada dato se puede comprobar con fuentes confiables (instituciones, revistas científicas, medios serios). Si una afirmación popular no se puede comprobar, el guion la presenta como "dicen que…" y lo aclara, nunca como hecho.
  4. Cada escena (≈3 s) dice una sola idea que se puede dibujar con los assets disponibles o con un asset nuevo razonable.
  5. Los objetos protagonistas y la paleta son distintos a los de los últimos videos.
  6. El final conecta con el inicio (bucle) o deja una frase memorable.

## 3. Verificar datos
Busca en la web cada cifra, fecha y afirmación. Prefiere fuentes primarias o institucionales. Si dos fuentes se contradicen, usa la más conservadora o quita el dato. Guarda las URLs de las fuentes en `meta.fuentes`.

## 4. Construir cada proyecto
Formato: JSON con `settings`, `scenes` y `meta`. Ajustes obligatorios:
`{"theme":"oscuro","tts_engine":"edge","caption_style":"suave","caption_size":92,"sfx":"auto","sfx_volume":0.5,"voice_speed":1.08,"trim_silences":true,"scene_pad":0.15,"transition_seconds":0.35}`
`meta`: `{"titulo": "...", "tema": "familia / subtema", "fuentes": ["https://..."]}`.

Reglas de diseño:
- **Duración:** 10–13 escenas, 120–150 palabras (≈40–50 s con la voz real). Ninguna escena con más de ~5 s de voz seguida.
- **Escena 1** = gancho (texto grande con pop+shake). **Última escena** = mismo diseño que la primera con el texto cambiado, para que haga loop.
- **Objeto principal visible desde el segundo 0** (`at: 0.05`). Evita escenas que empiezan vacías por esperar una palabra.
- Fondos y transiciones variados: no repetir el mismo fondo más de 2 escenas seguidas. Mezcla `push`, `whip`, `zoom_in`, `slide`, `wipe`, `cut`, `flash`.
- Texto de pantalla en `texto` (y=0.86–0.9 como máximo); deja libre y<0.2 para los subtítulos.
- No repitas el mismo personaje o asset protagonista en más de 3 escenas.
- Los números con símbolos (%, °C) van en pantalla; en la narración se escriben como se leen ("setenta por ciento", "un doceavo") para que la voz los diga bien.
- Si falta un asset, créalo en `vstudio/vector_assets.py` (función `a_nombre(w, p)`, registro en `ASSETS`) siguiendo el estilo de los existentes; revisa su aspecto con `python3 cli.py preview proyecto.json --scene N --t T -o salida.png` (`--scene` empieza en 0).

## 5. Revisar cada proyecto
1. `python3 cli.py revisar archivo.json` debe terminar **sin errores y, idealmente, sin avisos**. Arregla los avisos que se puedan.
2. Vista previa de cada escena (al menos t=1 s y t=2.5 s): sin elementos tapados, sin cortes, texto legible, nada fuera de pantalla.
3. Render de prueba silencioso (`tts_engine: "silencio"`, `--encoder x264 --quality borrador`) del primer proyecto para confirmar que no falla. No hay red para TTS en el entorno: la voz real la genera el programa en la PC de Omar.
4. Si un proyecto no pasa la revisión después de dos intentos, descártalo y reemplázalo por otro tema; si no hay tiempo, deja 3 y anótalo.

## 6. Entrega
- Archivos: `proyectos_diarios/AAAA-MM-DD/01_tema.json`, `02_...`, `03_...`, `04_...` (nombres cortos sin acentos).
- `proyectos_diarios/AAAA-MM-DD/NOTAS.md`: por proyecto, 2–3 líneas con el giro, las fuentes más importantes, los assets nuevos creados y cualquier duda sobre un dato.
- Actualiza `proyectos_diarios/_temas_usados.md` (una línea por tema: fecha, familia, título).
- Sube los cambios con commit a `main` (`git add proyectos_diarios vstudio ...`). Si hubo assets nuevos, súbelos en el mismo commit y sube la versión en `vstudio/__init__.py` (+0.0.1). Mensaje: `Proyectos diarios AAAA-MM-DD`.
- No modifiques el motor, la interfaz ni otros proyectos más allá de los assets nuevos necesarios.

## 7. Qué ve Omar
Al actualizar el programa, el botón «🆕 Proyectos nuevos» muestra los de cada día, con título, tema, duración aproximada y fuentes; «Abrir» carga el proyecto para renderizarlo y revisarlo.
