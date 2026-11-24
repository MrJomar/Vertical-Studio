"""Servidor local de Vertical Studio: API + interfaz (ventana tipo app con Edge/Chrome)."""
from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import os
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

from . import __version__
from . import tiles as T
from .core import (APP_DIR, CACHE_DIR, IMAGE_EXT, THEMES, VIDEO_EXT, ffmpeg_bin, nvenc_available, popen_kwargs,
                   run_quiet)
from .project import DEFAULT_SETTINGS, TRANSITIONS, Cancelled, Ctx, Project
from .scenes import SCENE_TYPES

UI_DIR = APP_DIR / "ui"
TOKEN = secrets.token_urlsafe(16)
LAST_PING = {"t": 0.0, "seen": False}

LABELS = {
    "cover": "Recortar", "blur": "Fondo difuminado", "face": "Seguir rostro",
    "zoom": "Zoom a país", "tour": "Visitar lugares", "route": "Ruta animada",
    "arc": "Arco", "line": "Línea recta", "": "Predeterminado del proyecto",
    "vectorial": "Vectorial (sin internet)", "personalizado": "Personalizado (URL propia)",
    "edge": "Edge (voz neuronal, internet)", "sapi": "Windows (sin internet)", "silencio": "Sin voz (solo subtítulos)",
    "auto": "Automático", "nvenc": "NVIDIA NVENC", "x264": "CPU (x264)",
    "borrador": "Borrador", "normal": "Normal", "alta": "Alta", "maxima": "Máxima",
    "fade": "Fundido", "slide": "Deslizar", "zoom_t": "Zoom", "flash": "Destello", "wipe": "Cortinilla", "cut": "Corte",
    "neon": "Neón", "oscuro": "Oscuro", "retro": "Retro", "papel": "Papel", "esmeralda": "Esmeralda",
}
for k, v in T.PROVIDERS.items():
    LABELS[k] = v["label"]

VOICES = ["es-MX-JorgeNeural", "es-MX-DaliaNeural", "es-ES-AlvaroNeural", "es-ES-ElviraNeural", "es-AR-TomasNeural",
          "es-CO-GonzaloNeural", "es-US-AlonsoNeural", "es-CL-LorenzoNeural", "en-US-GuyNeural", "en-US-JennyNeural"]

SETTINGS_GROUPS = [
    ("Apariencia", [("theme", "Tema visual", "theme", "oscuro", list(THEMES.keys())),
                    ("watermark", "Marca de agua (p. ej. @tucanal)", "text", "")]),
    ("Voz", [("tts_engine", "Motor de voz", "choice", "edge", ["edge", "sapi", "silencio"]),
             ("voice", "Voz (Edge)", "combo", "es-MX-JorgeNeural", VOICES),
             ("tts_rate", "Velocidad de la voz (%)", "number", 0)]),
    ("Subtítulos", [("caption_size", "Tamaño", "number", 78), ("caption_y", "Posición vertical (0 a 1)", "number", 0.80)]),
    ("Mapas", [("map_style", "Estilo de mapa por defecto", "choice", "satelite", T.STYLE_CHOICES),
               ("map_tile_url", "URL de teselas propia (opcional): https://…/{z}/{x}/{y}.png", "text", ""),
               ("map_grade", "Color del mapa (vivo = más saturado)", "choice", "", ["", "vivo", "cine"]),
               ("map_attribution", "Mostrar atribución del mapa", "bool", True)]),
    ("Transiciones y música", [("transition", "Transición entre escenas", "choice", "fade", TRANSITIONS),
                               ("transition_seconds", "Duración de la transición (s)", "number", 0.3),
                               ("music", "Música de fondo", "file", ""),
                               ("music_volume", "Volumen de la música (0 a 1)", "number", 0.12)]),
    ("Salida", [("encoder", "Codificador de video", "choice", "auto", ["auto", "nvenc", "x264"]),
                ("quality", "Calidad", "choice", "alta", ["borrador", "normal", "alta", "maxima"]),
                ("fps", "Cuadros por segundo", "choice", 30, [24, 30, 60]),
                ("whisper_model", "Modelo Whisper (subtítulos y clipping)", "choice", "small",
                 ["tiny", "base", "small", "medium", "large-v3"]),
                ("align_voice", "Subtítulos de voz IA: tiempos reales con Whisper (local)", "choice", "whisper", ["whisper", "estimado"])]),
]


def _label(v) -> str:
    if v == "zoom":
        return LABELS["zoom"]
    return LABELS.get(str(v), str(v))


def _field(f, scene_type: str | None = None) -> dict:
    key, label, kind, default = f[:4]
    ch = f[4] if len(f) > 4 else None
    d = {"key": key, "label": label, "kind": kind, "default": default}
    if ch is not None:
        lab = _label
        if key == "transition":
            lab = lambda v: {"zoom": "Zoom"}.get(v, LABELS.get(v, v))
        if key == "mode":
            lab = lambda v: {"zoom": "Zoom a país", "tour": "Visitar lugares", "route": "Ruta animada"}[v]
        d["choices"] = [{"value": c, "label": lab(c)} for c in ch]
    return d


def build_schema() -> dict:
    types = {}
    for k, info in SCENE_TYPES.items():
        types[k] = {"label": info["label"], "desc": info.get("desc", ""), "icon": info.get("icon", "film"),
                    "fields": [_field(f, k) for f in info["fields"]]}
    return {"version": __version__, "types": types, "order": list(SCENE_TYPES.keys()),
            "settings": [{"group": g, "fields": [_field(f) for f in fs]} for g, fs in SETTINGS_GROUPS],
            "themes": {k: {n: list(v[n]) for n in ("bg1", "bg2", "accent", "text")} for k, v in THEMES.items()},
            "defaults": DEFAULT_SETTINGS, "nvenc": nvenc_available(),
            "map_styles": [{"value": k, "label": v["label"]} for k, v in T.PROVIDERS.items()]}


# ----------------------------------------------------------------------------- diálogos de archivo
class Dialogs:
    """Hilo propio con tkinter solo para los selectores de archivos nativos de Windows."""

    FILTERS = {
        "media": [("Imágenes y videos", "*.jpg *.jpeg *.png *.webp *.bmp *.gif *.mp4 *.mov *.mkv *.webm *.avi"),
                  ("Todos", "*.*")],
        "image": [("Imágenes", "*.jpg *.jpeg *.png *.webp *.bmp *.gif"), ("Todos", "*.*")],
        "video": [("Videos", "*.mp4 *.mov *.mkv *.webm *.avi *.m4v"), ("Todos", "*.*")],
        "audio": [("Audio", "*.mp3 *.wav *.m4a *.aac *.ogg *.flac"), ("Todos", "*.*")],
        "json": [("Proyecto Vertical Studio", "*.json"), ("Todos", "*.*")],
        "geojson": [("GeoJSON", "*.geojson *.json"), ("Todos", "*.*")],
        "mp4": [("Video MP4", "*.mp4")],
        "any": [("Todos", "*.*")],
    }

    def __init__(self):
        self.q: queue.Queue = queue.Queue()
        self.ok: bool | None = None
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            self.ok = True
        except Exception:
            self.ok = False
            filedialog = None
            root = None
        while True:
            fn, out = self.q.get()
            if not self.ok:
                out.put(("err", "No hay selector de archivos disponible (tkinter)."))
                continue
            try:
                root.update()
                out.put(("ok", fn(filedialog)))
            except Exception as e:
                out.put(("err", str(e)))

    def call(self, fn, timeout: float = 600):
        out: queue.Queue = queue.Queue()
        self.q.put((fn, out))
        kind, val = out.get(timeout=timeout)
        if kind == "err":
            raise RuntimeError(val)
        return val

    def pick(self, kind: str, filt: str = "any", title: str = "", initial: str = "", default_ext: str = ".mp4"):
        ft = self.FILTERS.get(filt, self.FILTERS["any"])
        init_dir = initial if initial and os.path.isdir(initial) else None

        def run(fd):
            if kind == "files":
                return list(fd.askopenfilenames(title=title or "Elige archivos", filetypes=ft, initialdir=init_dir))
            if kind == "file":
                p = fd.askopenfilename(title=title or "Elige un archivo", filetypes=ft, initialdir=init_dir)
                return [p] if p else []
            if kind == "dir":
                p = fd.askdirectory(title=title or "Elige una carpeta", initialdir=init_dir)
                return [p] if p else []
            if kind == "save":
                p = fd.asksaveasfilename(title=title or "Guardar como", filetypes=ft, defaultextension=default_ext,
                                         initialfile=os.path.basename(initial) if initial and not init_dir else "",
                                         initialdir=init_dir or (os.path.dirname(initial) if initial else None))
                return [p] if p else []
            return []
        return self.call(run)


DIALOGS = Dialogs()


# ----------------------------------------------------------------------------- trabajos
class Job:
    name = ""

    def __init__(self):
        self.id = secrets.token_hex(6)
        self.state = "running"
        self.stage = "Preparando…"
        self.frac = 0.0
        self.result = None
        self.error = None
        self.cancel = False
        self.started = time.time()


JOBS: dict[str, Job] = {}
RECENT_FILE = CACHE_DIR / "recent.json"


def _recent() -> list:
    try:
        items = json.loads(RECENT_FILE.read_text("utf-8"))
    except Exception:
        items = []
    return [i for i in items if os.path.isfile(i.get("path", ""))][:24]


def _recent_add(path: str, prj: dict, rendered: str = "") -> None:
    try:
        items = [i for i in _recent() if i["path"] != path]
        old = next((i for i in _recent() if i["path"] == path), {})
        scs = prj.get("scenes") or []
        items.insert(0, {"path": path, "name": Path(path).stem, "ts": time.time(), "scenes": len(scs),
                         "types": sorted({s.get("type", "") for s in scs}),
                         "last_render": rendered or old.get("last_render", ""), "rendered_ts": time.time() if rendered else old.get("rendered_ts", 0)})
        RECENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        RECENT_FILE.write_text(json.dumps(items[:30], ensure_ascii=False), "utf-8")
    except Exception:
        pass


def start_job(fn) -> Job:
    job = Job()
    JOBS[job.id] = job

    def run():
        try:
            job.result = fn(job)
            job.state = "done"
            job.frac = 1.0
        except Cancelled:
            job.state = "cancelled"
        except Exception as e:
            job.state = "error"
            job.error = str(e)
            traceback.print_exc()
    threading.Thread(target=run, daemon=True).start()
    return job


def job_progress(job: Job):
    def cb(stage, frac):
        job.stage, job.frac = stage, float(frac)
    return cb


# ----------------------------------------------------------------------------- vista previa
_pcache: dict = {}
_plock = threading.Lock()


def preview_frame(data: dict, idx: int, t: float, width: int):
    project = Project(data["project"], data.get("path"))
    scenes = project.scenes
    if not (0 <= idx < len(scenes)):
        raise ValueError("Escena inexistente")
    st = dict(project.settings)
    st["tts_engine"] = "silencio"
    spec = scenes[idx]
    before = sum(1 for s in scenes[:idx] if s.get("type") == "top_item")
    total = sum(1 for s in scenes if s.get("type") == "top_item")
    base = project.base_dir
    key = hashlib.sha1(json.dumps([st, spec, before, total, base], sort_keys=True, default=str).encode()).hexdigest()
    with _plock:
        entry = _pcache.get(key)
        if entry is None:
            ctx = Ctx(st, base, preview=True)
            ctx.top_total = total
            sc = SCENE_TYPES[spec["type"]]["cls"](spec, ctx, idx)
            sc.top_index = before
            sc.prepare()
            entry = {"sc": sc, "key": key}
            _pcache[key] = entry
            while len(_pcache) > 8:
                old = _pcache.pop(next(iter(_pcache)))
                old["sc"].close()
        sc = entry["sc"]
        img = sc.frame(max(0.0, min(t, sc.duration))).convert("RGB")
        dur = sc.duration
        warns = list(sc.warnings)
    if width and width < img.width:
        img = img.resize((width, int(img.height * width / img.width)), Image.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=84)
    return buf.getvalue(), dur, warns


# ----------------------------------------------------------------------------- miniaturas
_thumbs: dict = {}


def thumb_bytes(path: str, w: int = 160) -> bytes:
    key = (path, w, os.path.getmtime(path))
    if key in _thumbs:
        return _thumbs[key]
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXT:
        im = Image.open(path)
        im.seek(0)
        im = im.convert("RGB")
        im.thumbnail((w, w * 2))
    elif ext in VIDEO_EXT:
        r = run_quiet([ffmpeg_bin(), "-v", "error", "-ss", "1", "-i", path, "-frames:v", "1", "-vf", f"scale={w}:-2",
                       "-f", "image2pipe", "-vcodec", "mjpeg", "-"])
        if not r.stdout:
            r = run_quiet([ffmpeg_bin(), "-v", "error", "-i", path, "-frames:v", "1", "-vf", f"scale={w}:-2",
                           "-f", "image2pipe", "-vcodec", "mjpeg", "-"])
        _thumbs[key] = r.stdout
        return r.stdout
    else:
        raise ValueError("tipo no soportado")
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=78)
    if len(_thumbs) > 300:
        _thumbs.clear()
    _thumbs[key] = buf.getvalue()
    return _thumbs[key]


# ----------------------------------------------------------------------------- ejemplos
def examples_catalog() -> list[dict]:
    from .examples import CATALOG, example_project
    out = []
    for ex in CATALOG:
        vid = None
        for base, url in ((UI_DIR / "examples", "/media/examples/"), (CACHE_DIR / "examples", "/media/cache_examples/")):
            if (base / f"{ex['id']}.mp4").exists():
                vid = url + f"{ex['id']}.mp4"
                break
        out.append({**{k: v for k, v in ex.items() if k != "build"}, "video": vid,
                    "project": example_project(ex["id"])})
    return out


def render_example(job: Job, ex_id: str):
    from .examples import example_project
    data = example_project(ex_id)
    data["settings"].update({"tts_engine": "silencio", "quality": "normal"})
    outdir = CACHE_DIR / "examples"
    outdir.mkdir(parents=True, exist_ok=True)
    tmp = outdir / f"{ex_id}_full.mp4"
    proj = Project(data, None)
    info = proj.render(str(tmp), job_progress(job), lambda: job.cancel)
    out = outdir / f"{ex_id}.mp4"
    run_quiet([ffmpeg_bin(), "-y", "-v", "error", "-i", str(tmp), "-vf", "scale=540:960", "-c:v", "libx264",
               "-crf", "26", "-preset", "veryfast", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out)])
    try:
        tmp.unlink()
    except OSError:
        pass
    return {"video": f"/media/cache_examples/{ex_id}.mp4", "warnings": info["warnings"]}


PRESETS_FILE = CACHE_DIR / "presets.json"


def _presets() -> dict:
    try:
        return json.loads(PRESETS_FILE.read_text("utf-8"))
    except Exception:
        return {}


# ----------------------------------------------------------------------------- HTTP
def _send_file(h: BaseHTTPRequestHandler, path: Path, ctype: str | None = None):
    size = path.stat().st_size
    ctype = ctype or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    rng = h.headers.get("Range")
    start, end, code = 0, size - 1, 200
    if rng:
        m = re.match(r"bytes=(\d*)-(\d*)", rng)
        if m:
            if m.group(1):
                start = int(m.group(1))
            if m.group(2):
                end = min(int(m.group(2)), size - 1)
            if not m.group(1) and m.group(2):
                start = max(0, size - int(m.group(2)))
                end = size - 1
            code = 206
    h.send_response(code)
    h.send_header("Content-Type", ctype)
    h.send_header("Accept-Ranges", "bytes")
    h.send_header("Content-Length", str(end - start + 1))
    if code == 206:
        h.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    try:
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                h.wfile.write(chunk)
                left -= len(chunk)
    except (BrokenPipeError, ConnectionResetError):
        pass


class Handler(BaseHTTPRequestHandler):
    server_version = "VerticalStudio"
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # silencioso
        pass

    # ---- utilidades
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _auth(self, q) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            return False
        tok = self.headers.get("X-VS-Token") or (q.get("k") or [""])[0]
        return secrets.compare_digest(tok, TOKEN)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}

    # ---- GET
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        path = u.path
        try:
            if path in ("/", "/index.html"):
                html = (UI_DIR / "index.html").read_text("utf-8").replace("__TOKEN__", TOKEN)
                return self._bytes(html.encode("utf-8"), "text/html; charset=utf-8")
            if path == "/favicon.ico":
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if path in ("/app.js", "/style.css"):
                return _send_file(self, UI_DIR / path.lstrip("/"))
            if not self._auth(q):
                return self._json({"error": "no autorizado"}, 403)
            if path == "/api/ping":
                LAST_PING["t"], LAST_PING["seen"] = time.time(), True
                return self._json({"ok": True})
            if path == "/api/schema":
                return self._json(build_schema())
            if path == "/api/job":
                j = JOBS.get((q.get("id") or [""])[0])
                if not j:
                    return self._json({"error": "trabajo inexistente"}, 404)
                return self._json({"state": j.state, "stage": j.stage, "frac": j.frac, "error": j.error,
                                   "result": j.result, "elapsed": time.time() - j.started})
            if path == "/api/ai_prompt":
                from .vector import ai_prompt
                return self._json({"prompt": ai_prompt((q.get("style") or [""])[0])})
            if path == "/api/kit":
                from vstudio import svgkit
                return self._json({"piezas": svgkit.scan()})
            if path == "/api/kit_prompt":
                from vstudio import svgkit
                return self._json({"prompt": svgkit.kit_prompt((q.get("style") or [""])[0])})
            if path == "/api/styles":
                from . import styles as ST
                return self._json({"styles": ST.list_styles((q.get("tipo") or [None])[0])})
            if path == "/api/script_prompt":
                from . import styles as ST
                return self._json({"prompt": ST.script_prompt((q.get("style") or [""])[0], (q.get("tema") or [""])[0], (q.get("canal") or [""])[0])})
            if path == "/api/voices":
                from . import voices as V
                eng = (q.get("engine") or ["edge"])[0]
                return self._json({"voices": V.list_voices(eng), "config": V.public(),
                                   "gemini": V.gemini_models() if eng == "gemini" else None})
            if path == "/api/voice_config":
                from . import voices as V
                return self._json(V.public())
            if path == "/api/voice_audio":
                f = os.path.basename((q.get("f") or [""])[0])
                fp = CACHE_DIR / "tts" / f
                if not f or not fp.exists():
                    return self._json({"error": "no existe"}, 404)
                return _send_file(self, fp)
            if path == "/api/jobs":
                return self._json({"jobs": [{"id": j.id, "state": j.state, "stage": j.stage, "frac": j.frac, "error": j.error,
                                             "elapsed": time.time() - j.started, "name": getattr(j, "name", ""),
                                             "out": (j.result or {}).get("path") if isinstance(j.result, dict) else None}
                                            for j in sorted(JOBS.values(), key=lambda j: -j.started)[:30]]})
            if path == "/api/recent":
                return self._json({"recent": _recent()})
            if path == "/api/update_check":
                from . import updater
                return self._json(updater.check())
            if path == "/api/presets":
                return self._json(_presets())
            if path == "/api/examples":
                return self._json(examples_catalog())
            if path == "/api/thumb":
                p = (q.get("path") or [""])[0]
                if not os.path.isfile(p) or Path(p).suffix.lower() not in (IMAGE_EXT | VIDEO_EXT):
                    return self._json({"error": "no existe"}, 404)
                return self._bytes(thumb_bytes(p, int((q.get("w") or ["160"])[0])), "image/jpeg",
                                   {"Cache-Control": "max-age=300"})
            if path == "/api/default_out":
                name = re.sub(r"[^\w\- ]", "", (q.get("name") or ["video"])[0]).strip() or "video"
                d = Path.home() / "Videos" / "VerticalStudio"
                d.mkdir(parents=True, exist_ok=True)
                return self._json({"path": str(d / f"{name}_{time.strftime('%Y%m%d_%H%M')}.mp4")})
            if path == "/api/video":
                p = Path((q.get("path") or [""])[0])
                if p.is_file() and p.suffix.lower() in VIDEO_EXT:
                    return _send_file(self, p)
                return self._json({"error": "no existe"}, 404)
            if path.startswith("/media/examples/"):
                p = UI_DIR / "examples" / path.split("/")[-1]
                return _send_file(self, p) if p.is_file() else self._json({"error": "no existe"}, 404)
            if path.startswith("/media/cache_examples/"):
                p = CACHE_DIR / "examples" / path.split("/")[-1]
                return _send_file(self, p) if p.is_file() else self._json({"error": "no existe"}, 404)
            return self._json({"error": "ruta desconocida"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": str(e)}, 500)

    # ---- POST
    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if not self._auth(q):
            return self._json({"error": "no autorizado"}, 403)
        try:
            d = self._body()
            path = u.path
            if path == "/api/preview":
                body, dur, warns = preview_frame(d, int(d["scene"]), float(d.get("t", 1.5)), int(d.get("w", 540)))
                return self._bytes(body, "image/jpeg", {"X-Duration": f"{dur:.2f}",
                                                         "X-Warn": urllib.parse.quote(" | ".join(warns))})
            if path == "/api/pick":
                paths = DIALOGS.pick(d.get("kind", "file"), d.get("filter", "any"), d.get("title", ""),
                                     d.get("initial", ""), d.get("ext", ".mp4"))
                return self._json({"paths": paths})
            if path == "/api/open_project":
                if d.get("path"):
                    ps = [d["path"]]
                    if not os.path.isfile(ps[0]):
                        return self._json({"error": "El archivo ya no existe."}, 404)
                else:
                    ps = DIALOGS.pick("file", "json", "Abrir proyecto")
                if not ps:
                    return self._json({"cancelled": True})
                prj = json.loads(Path(ps[0]).read_text("utf-8"))
                _recent_add(ps[0], prj)
                return self._json({"path": ps[0], "project": prj})
            if path == "/api/save_project":
                p = d.get("path")
                if not p:
                    ps = DIALOGS.pick("save", "json", "Guardar proyecto", d.get("suggest", "proyecto.json"), ".json")
                    if not ps:
                        return self._json({"cancelled": True})
                    p = ps[0]
                Path(p).write_text(json.dumps(d["project"], ensure_ascii=False, indent=2), "utf-8")
                _recent_add(p, d["project"])
                return self._json({"path": p})
            if path == "/api/render":
                proj = Project(d["project"], d.get("path"))
                out = d["out"]

                def job_fn(job):
                    return proj.render(out, job_progress(job), lambda: job.cancel)
                jb = start_job(job_fn)
                jb.name = d.get("name") or os.path.basename(out)
                if d.get("path"):
                    _recent_add(d["path"], d["project"], rendered=out)
                return self._json({"id": jb.id})
            if path == "/api/cancel":
                j = JOBS.get(d.get("id", ""))
                if j:
                    j.cancel = True
                return self._json({"ok": True})
            if path == "/api/script":
                from .scriptsplit import split_script
                r = split_script(d.get("text", ""), d.get("title", ""), bool(d.get("countdown", True)),
                                 d.get("media_dir", ""), int(d.get("max_words", 38)), False)
                return self._json({"scenes": r["scenes"]})
            if path == "/api/vector_ai":
                from .vector import ai_prompt
                import urllib.request as ur
                prompt = ai_prompt(d.get("style", "")) + "\nGUION:\n" + d.get("script", "")
                body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                                   "generationConfig": {"responseMimeType": "application/json"}}).encode()
                model = d.get("model") or "gemini-2.5-flash"
                req = ur.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={d['key']}",
                                 data=body, headers={"Content-Type": "application/json"})
                with ur.urlopen(req, timeout=180) as r:
                    res = json.loads(r.read().decode())
                txt = res["candidates"][0]["content"]["parts"][0]["text"]
                scenes = json.loads(txt)
                if isinstance(scenes, dict):
                    scenes = scenes.get("scenes", [scenes])
                for sc in scenes:
                    sc["type"] = "vector"
                return self._json({"scenes": scenes})
            if path == "/api/voice_save":
                from . import voices as V
                upd = {}
                for k in ("gemini_key", "gemini_model", "type_defaults", "img_key", "img_model"):
                    if k in d and not (k in ("gemini_key", "img_key") and not d[k]):
                        upd[k] = d[k]
                V.save(upd)
                if d.get("delete_profile"):
                    V.delete_profile(d["delete_profile"])
                if d.get("profile_name"):
                    V.save_profile(d["profile_name"], d.get("profile") or {})
                return self._json(V.public())
            if path == "/api/img_clear_key":
                from . import voices as V
                V.save({"img_key": ""})
                return self._json(V.public())
            if path == "/api/img_test":
                from . import voices as V
                import urllib.request as ur
                import urllib.error as ue
                key = d.get("key") or V.get_img_key()
                model = d.get("model") or V.load().get("img_model") or V.IMG_MODEL_DEFAULT
                if not key:
                    return self._json({"ok": False, "error": "No hay API key: pega una aquí o guarda la de Gemini."})
                body = json.dumps({"contents": [{"parts": [{"text": "Responde solo: ok"}]}]}).encode()
                req = ur.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                                 data=body, headers={"Content-Type": "application/json"})
                try:
                    with ur.urlopen(req, timeout=60) as r:
                        json.loads(r.read().decode())
                    return self._json({"ok": True, "model": model})
                except ue.HTTPError as e:
                    msg = {400: "La clave no es válida.", 403: "La clave no tiene permiso para ese modelo.", 404: "Ese modelo no existe o no está disponible para tu clave.",
                           429: "Se acabó el cupo por ahora (límite de la API)."}.get(e.code, f"Error {e.code} de Google.")
                    return self._json({"ok": False, "error": msg})
                except Exception as e:
                    return self._json({"ok": False, "error": f"No se pudo conectar: {e}"})
            if path == "/api/voice_clear_key":
                from . import voices as V
                V.save({"gemini_key": ""})
                return self._json(V.public())
            if path == "/api/voice_test":
                from . import audio as AU
                txt = d.get("text") or "Hola, así suena esta voz en tus videos."
                eng = d.get("engine") or "edge"
                a, _, dur = AU.synthesize(txt, eng, d.get("voice") or "", int(d.get("rate") or 0), d.get("model") or "", d.get("style") or "")
                return self._json({"file": os.path.basename(a) if a else None, "duration": dur})
            if path == "/api/update_config":
                from . import updater
                updater.save_config({k: d[k] for k in ("check_updates", "auto_update", "update_repo", "update_token") if k in d})
                return self._json(updater.check())
            if path == "/api/preset_save":
                pr = _presets()
                pr[d["name"]] = d["settings"]
                PRESETS_FILE.parent.mkdir(parents=True, exist_ok=True)
                PRESETS_FILE.write_text(json.dumps(pr, ensure_ascii=False, indent=2), "utf-8")
                return self._json({"presets": pr})
            if path == "/api/preset_delete":
                pr = _presets()
                pr.pop(d.get("name", ""), None)
                PRESETS_FILE.write_text(json.dumps(pr, ensure_ascii=False, indent=2), "utf-8")
                return self._json({"presets": pr})
            if path == "/api/autoclip":
                def job_fn(job):
                    from . import clipper
                    st = d.get("settings", {})
                    clips = clipper.analyze(d["video"], int(d.get("n", 5)), float(d.get("lo", 20)),
                                            float(d.get("hi", 55)), st.get("whisper_model", "small"),
                                            d.get("language") or None, d.get("gemini_key") or None,
                                            progress=lambda f: job_progress(job)("Transcribiendo y analizando…", f))
                    return {"scenes": clipper.to_scenes(d["video"], clips, d.get("fit", "blur")), "clips": clips}
                return self._json({"id": start_job(job_fn).id})
            if path == "/api/example_render":
                ex_id = d["id"]
                return self._json({"id": start_job(lambda job: render_example(job, ex_id)).id})
            if path == "/api/update_apply":
                from . import updater
                return self._json(updater.apply())
            if path == "/api/restart":
                def _restart():
                    time.sleep(0.8)
                    exe = sys.executable
                    kw = {}
                    if os.name == "nt":
                        pw = exe.replace("python.exe", "pythonw.exe")
                        exe = pw if os.path.exists(pw) else exe
                        kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
                    subprocess.Popen([exe, str(APP_DIR / "app.py")], cwd=str(APP_DIR), **kw)
                    time.sleep(0.4)
                    os._exit(0)
                threading.Thread(target=_restart, daemon=True).start()
                return self._json({"ok": True})
            if path == "/api/open_url":
                u = d.get("url", "")
                if u.startswith("https://github.com/"):
                    webbrowser.open(u)
                return self._json({"ok": True})
            if path == "/api/reveal":
                p = d.get("path", "")
                if os.name == "nt":
                    if d.get("play"):
                        os.startfile(p)  # type: ignore[attr-defined]
                    else:
                        subprocess.Popen(["explorer", "/select,", os.path.normpath(p)])
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", "-R", p])
                else:
                    subprocess.Popen(["xdg-open", os.path.dirname(p)])
                return self._json({"ok": True})
            return self._json({"error": "ruta desconocida"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": str(e)}, 500)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# ----------------------------------------------------------------------------- arranque
def _find_browser() -> str | None:
    cands: list[str] = []
    if os.name == "nt":
        for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                cands += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                          os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    else:
        cands += [shutil.which(n) or "" for n in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser")]
    return next((c for c in cands if c and os.path.exists(c)), None)


def open_window(url: str) -> None:
    exe = _find_browser()
    if exe:
        prof = CACHE_DIR / "browser_profile"
        prof.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen([exe, f"--app={url}", "--window-size=1520,940", f"--user-data-dir={prof}",
                              "--no-first-run", "--no-default-browser-check"], **popen_kwargs())
            return
        except OSError:
            pass
    webbrowser.open(url)


def main(open_ui: bool = True, port: int = 0) -> None:
    srv = Server(("127.0.0.1", port), Handler)
    port = srv.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    print(f"Vertical Studio {__version__} — {url}")
    print("Cierra la ventana de la app para terminar (o Ctrl+C aquí).")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    if open_ui:
        open_window(url)
    try:
        start = time.time()
        while True:
            time.sleep(2)
            busy = any(j.state == "running" for j in JOBS.values())
            if open_ui and not busy:
                if LAST_PING["seen"] and time.time() - LAST_PING["t"] > 150:
                    break
                if not LAST_PING["seen"] and time.time() - start > 90:
                    break
    except KeyboardInterrupt:
        pass
    os._exit(0)
