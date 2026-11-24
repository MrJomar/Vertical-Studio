"""Tablero: lista unificada de proyectos (GitHub + locales), estado por proyecto y cola que sobrevive al cierre."""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

from .core import APP_DIR, CACHE_DIR

STATE_FILE = CACHE_DIR / "tablero.json"
DAILY_DIR = APP_DIR / "proyectos_diarios"
LOCK = threading.RLock()

STYLES = [("animacion", "Animación vertical"), ("mapas", "Mapas"), ("broll", "B-roll con voz"),
          ("clips", "Clips de video"), ("otros", "Otros")]
STYLE_LABEL = dict(STYLES)
GH_ID = re.compile(r"^\d{4}-\d{2}-\d{2}/[\w\-.]+\.json$")
ESTADOS = ("pendiente", "en_cola", "renderizando", "listo", "error")


def style_of(scenes: list) -> str:
    types = {s.get("type") for s in scenes or []}
    for t, k in (("vector", "animacion"), ("map", "mapas"), ("broll", "broll"), ("clip", "clips")):
        if t in types:
            return k
    return "otros"


def content_hash(data: dict) -> str:
    raw = json.dumps({"settings": data.get("settings", {}), "scenes": data.get("scenes", [])}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# ----------------------------------------------------------------------------- estado en disco
def _load() -> dict:
    try:
        d = json.loads(STATE_FILE.read_text("utf-8"))
        if isinstance(d, dict):
            d.setdefault("items", {})
            d.setdefault("queue", [])
            d.setdefault("paused", False)
            return d
    except Exception:
        pass
    return {"items": {}, "queue": [], "paused": False}


def _save(st: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(STATE_FILE)


def get_state() -> dict:
    with LOCK:
        return _load()


def set_item(item_id: str, **fields) -> dict:
    with LOCK:
        st = _load()
        it = st["items"].setdefault(item_id, {})
        it.update(fields)
        it["ts"] = time.time()
        _save(st)
        return it


def set_paused(paused: bool) -> None:
    with LOCK:
        st = _load()
        st["paused"] = bool(paused)
        _save(st)


# ----------------------------------------------------------------------------- proyectos
def resolve(item_id: str, recent: list | None = None) -> Path | None:
    """Ruta de un proyecto a partir de su id (solo ids conocidos: sin rutas arbitrarias)."""
    if item_id.startswith("gh:"):
        rel = item_id[3:]
        if not GH_ID.match(rel):
            return None
        p = (DAILY_DIR / rel).resolve()
        return p if DAILY_DIR.resolve() in p.parents and p.is_file() else None
    if item_id.startswith("loc:"):
        path = item_id[4:]
        if any(r.get("path") == path for r in (recent or [])) and os.path.isfile(path):
            return Path(path)
    return None


def load_project(item_id: str, recent: list | None = None) -> tuple[dict, str] | None:
    p = resolve(item_id, recent)
    if not p:
        return None
    try:
        data = json.loads(p.read_text("utf-8"))
    except Exception:
        return None
    return {"settings": data.get("settings", {}), "scenes": data.get("scenes", []), "meta": data.get("meta", {})}, str(p)


def _entry(item_id: str, origin: str, path: Path, fecha: str, st_item: dict, data: dict) -> dict:
    scenes = data.get("scenes") or []
    meta = data.get("meta") or {}
    words = sum(len(str(s.get("narration", "")).split()) for s in scenes)
    h = content_hash(data)
    estado = st_item.get("estado", "pendiente")
    video = st_item.get("video", "")
    modificado = False
    if estado == "listo" and (st_item.get("hash") != h or not video or not os.path.isfile(video)):
        estado, modificado = "pendiente", True
    if estado not in ESTADOS:
        estado = "pendiente"
    style = style_of(scenes)
    title = meta.get("titulo") or (str(scenes[0].get("narration", ""))[:70] if scenes else path.stem)
    return {"id": item_id, "origen": origin, "fecha": fecha, "titulo": title, "tema": meta.get("tema", ""),
            "descripcion": meta.get("descripcion", ""), "hashtags": meta.get("hashtags", []),
            "fuentes": meta.get("fuentes", []), "estilo": style, "estilo_label": STYLE_LABEL[style],
            "escenas": len(scenes), "palabras": words, "segundos_aprox": round(words / 2.9) if words else 0,
            "hash": h, "estado": estado, "modificado": modificado, "video": video if estado == "listo" else "",
            "error": st_item.get("error", "") if estado == "error" else "", "pub": st_item.get("pub") or {},
            "path": str(path), "ts_listo": st_item.get("ts_listo", 0)}


def scan(recent: list) -> list[dict]:
    """Proyectos de GitHub (proyectos_diarios/) y los abiertos/guardados recientemente, con su estado."""
    st = get_state()["items"]
    out, seen_paths = [], set()
    if DAILY_DIR.is_dir():
        for day in sorted((d for d in DAILY_DIR.iterdir() if d.is_dir()), reverse=True):
            for f in sorted(day.glob("*.json")):
                try:
                    data = json.loads(f.read_text("utf-8"))
                except Exception:
                    continue
                iid = f"gh:{day.name}/{f.name}"
                out.append(_entry(iid, "github", f, day.name, st.get(iid, {}), data))
                seen_paths.add(str(f.resolve()))
    for r in recent:
        p = r.get("path", "")
        try:
            rp = str(Path(p).resolve())
        except OSError:
            continue
        if rp in seen_paths or not os.path.isfile(p):
            continue
        try:
            data = json.loads(Path(p).read_text("utf-8"))
        except Exception:
            continue
        iid = f"loc:{p}"
        fecha = time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(p)))
        out.append(_entry(iid, "local", Path(p), fecha, st.get(iid, {}), data))
    return out


# ----------------------------------------------------------------------------- cola persistente
def enqueue(ids: list[str]) -> int:
    n = 0
    with LOCK:
        st = _load()
        for i in ids:
            it = st["items"].setdefault(i, {})
            if it.get("estado") in ("en_cola", "renderizando"):
                continue
            it.update(estado="en_cola", error="", ts=time.time())
            if i not in st["queue"]:
                st["queue"].append(i)
            n += 1
        _save(st)
    return n


def dequeue(item_id: str) -> None:
    with LOCK:
        st = _load()
        st["queue"] = [i for i in st["queue"] if i != item_id]
        it = st["items"].get(item_id)
        if it and it.get("estado") == "en_cola":
            it["estado"] = "pendiente"
        _save(st)


def next_queued() -> str | None:
    with LOCK:
        st = _load()
        for i in st["queue"]:
            if st["items"].get(i, {}).get("estado") == "en_cola":
                return i
    return None


def finish(item_id: str, estado: str, **extra) -> None:
    """Marca el resultado y saca el proyecto de la cola."""
    with LOCK:
        st = _load()
        st["queue"] = [i for i in st["queue"] if i != item_id]
        it = st["items"].setdefault(item_id, {})
        it.update(estado=estado, ts=time.time(), **extra)
        _save(st)


def recover_on_start() -> int:
    """Tras un cierre inesperado: lo que estaba renderizando vuelve al inicio de la cola y la cola queda en pausa."""
    with LOCK:
        st = _load()
        broken = [i for i, it in st["items"].items() if it.get("estado") == "renderizando"]
        for i in broken:
            st["items"][i]["estado"] = "en_cola"
            st["queue"] = [i] + [q for q in st["queue"] if q != i]
        pending = [i for i in st["queue"] if st["items"].get(i, {}).get("estado") == "en_cola"]
        st["queue"] = pending
        st["paused"] = bool(pending)
        _save(st)
        return len(pending)


# ----------------------------------------------------------------------------- GitHub
def sync_github(fetch=None) -> dict:
    """Descarga los proyectos NUEVOS de proyectos_diarios/ del repositorio (sin actualizar el programa)."""
    from . import updater
    cfg = updater.load_config()
    repo, tok = cfg["update_repo"], cfg["update_token"]
    get = fetch or updater._get
    tree = json.loads(get(f"https://api.github.com/repos/{repo}/git/trees/main?recursive=1", tok))
    new, skipped = [], 0
    for node in tree.get("tree", []):
        p = node.get("path", "")
        if node.get("type") != "blob" or not p.startswith("proyectos_diarios/"):
            continue
        rel = p[len("proyectos_diarios/"):]
        if not (GH_ID.match(rel) or re.fullmatch(r"\d{4}-\d{2}-\d{2}/NOTAS\.md", rel)):
            continue
        dest = (DAILY_DIR / rel)
        if dest.exists():
            skipped += 1
            continue
        raw = get(f"https://api.github.com/repos/{repo}/contents/{p}", tok, "application/vnd.github.raw")
        if rel.endswith(".json"):
            json.loads(raw.decode("utf-8"))          # solo guarda JSON válido
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        if rel.endswith(".json"):
            new.append(rel)
    return {"nuevos": len(new), "archivos": new, "existentes": skipped}
