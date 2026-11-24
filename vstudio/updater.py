"""Búsqueda de actualizaciones en GitHub (repositorio público o privado con token de solo lectura)."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from . import __version__
from .core import APP_DIR, CACHE_DIR

CONFIG_FILE = CACHE_DIR / "config.json"
DEFAULTS = {"check_updates": True, "auto_update": True, "update_repo": "MrJomar/Vertical-Studio", "update_token": ""}


def load_config() -> dict:
    try:
        d = json.loads(CONFIG_FILE.read_text("utf-8"))
    except Exception:
        d = {}
    return {**DEFAULTS, **d}


def save_config(new: dict) -> dict:
    cfg = load_config()
    for k in DEFAULTS:
        if k in new:
            cfg[k] = new[k]
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
    return cfg


def _ver(s: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", s)[:4]) or (0,)


def _get(url: str, token: str, accept: str = "application/vnd.github+json") -> bytes:
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "VerticalStudio",
                                               **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=8) as r:
        return r.read()


def check(fetch=_get) -> dict:
    """Devuelve {enabled, current, latest, newer, url, notes, error}."""
    cfg = load_config()
    out = {"enabled": bool(cfg["check_updates"]), "current": __version__, "latest": None, "newer": False,
           "url": f"https://github.com/{cfg['update_repo']}", "notes": "", "error": None,
           "has_token": bool(cfg["update_token"]), "repo": cfg["update_repo"], "auto": bool(cfg["auto_update"])}
    if not out["enabled"]:
        return out
    repo, tok = cfg["update_repo"], cfg["update_token"]
    try:
        raw = fetch(f"https://api.github.com/repos/{repo}/contents/vstudio/__init__.py", tok, "application/vnd.github.raw")
        m = re.search(r"__version__\s*=\s*[\"']([^\"']+)[\"']", raw.decode("utf-8", "replace"))
        if not m:
            raise ValueError("no encontré la versión en el repositorio")
        out["latest"] = m.group(1)
        out["newer"] = _ver(m.group(1)) > _ver(__version__)
        if out["newer"]:
            try:
                c = json.loads(fetch(f"https://api.github.com/repos/{repo}/commits?per_page=1", tok))
                out["notes"] = (c[0]["commit"]["message"] or "").split("\n")[0][:160]
            except Exception:
                pass
    except urllib.error.HTTPError as e:
        out["error"] = ("El repositorio es privado: pon un token de solo lectura en Ajustes → Actualizaciones."
                        if e.code in (401, 403, 404) and not tok else f"GitHub respondió {e.code}.")
    except Exception as e:
        out["error"] = f"No se pudo comprobar ({e.__class__.__name__})."
    return out


SKIP_TOP = {"cache", ".git", ".github", "__pycache__"}


def apply(dest=APP_DIR, fetch=None) -> dict:
    """Descarga la última versión del repositorio y copia sus archivos sobre la carpeta del programa.

    No toca `cache/` (ajustes, mapas, plantillas) ni archivos que no estén en el repositorio (tus proyectos).
    Antes guarda una copia de seguridad en cache/backup/.
    """
    import io
    import shutil
    import time
    import zipfile
    from pathlib import Path

    cfg = load_config()
    if fetch is None:
        def fetch(url, tok):
            return _get(url, tok, "application/vnd.github+json")
    raw = fetch(f"https://api.github.com/repos/{cfg['update_repo']}/zipball/main", cfg["update_token"])
    dest = Path(dest)
    zf = zipfile.ZipFile(io.BytesIO(raw))
    names = [n for n in zf.namelist() if not n.endswith("/")]
    root = names[0].split("/")[0] + "/"
    if not any(n == root + "vstudio/__init__.py" for n in names):
        raise ValueError("El paquete descargado no parece ser Vertical Studio.")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    bak = Path(CACHE_DIR) / "backup" / f"{__version__}_{stamp}"
    n_copied = 0
    for n in names:
        rel = n[len(root):]
        if not rel or rel.split("/")[0] in SKIP_TOP:
            continue
        target = (dest / rel).resolve()
        if dest.resolve() not in target.parents:       # protección contra rutas maliciosas
            continue
        if target.exists() and not rel.startswith("ui/examples/"):
            b = bak / rel
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, b)
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(n) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)
        n_copied += 1
    # conserva solo las 3 copias de seguridad más recientes
    try:
        old = sorted((Path(CACHE_DIR) / "backup").iterdir())[:-3]
        for d in old:
            shutil.rmtree(d, ignore_errors=True)
    except OSError:
        pass
    return {"files": n_copied, "backup": str(bak)}
