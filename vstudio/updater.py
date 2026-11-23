"""Búsqueda de actualizaciones en GitHub (repositorio público o privado con token de solo lectura)."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from . import __version__
from .core import CACHE_DIR

CONFIG_FILE = CACHE_DIR / "config.json"
DEFAULTS = {"check_updates": True, "update_repo": "MrJomar/Vertical-Studio", "update_token": ""}


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
           "has_token": bool(cfg["update_token"]), "repo": cfg["update_repo"]}
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
