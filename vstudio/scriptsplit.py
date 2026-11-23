"""Convierte un guion en texto a escenas (Top numerado o B-roll por párrafos) y empareja imágenes de una carpeta."""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

from .core import IMAGE_EXT, VIDEO_EXT

_NUM = re.compile(r"^\s*(?:#|n[úu]mero\s+|lugar\s+|puesto\s+|top\s+)?(\d{1,3})\s*[\.\)\-:–—]\s*(.+)$", re.I)
_NUM2 = re.compile(r"^\s*(?:n[úu]mero|lugar|puesto|top)\s+(\d{1,3})\s*[:\-–—\.]?\s*(.*)$", re.I)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[\.\!\?…])\s+", text.strip()) if s.strip()]


def _chunk(text: str, max_words: int) -> list[str]:
    out, cur, n = [], [], 0
    for s in _sentences(text):
        w = len(s.split())
        if cur and n + w > max_words:
            out.append(" ".join(cur))
            cur, n = [], 0
        cur.append(s)
        n += w
    if cur:
        out.append(" ".join(cur))
    return out


def _numbered(line: str):
    m = _NUM.match(line) or _NUM2.match(line)
    if not m:
        return None
    title = m.group(2).strip()
    return m.group(1), title


def list_media(folder: str) -> list[str]:
    if not folder or not os.path.isdir(folder):
        return []
    files = [str(p) for p in sorted(Path(folder).iterdir(), key=lambda p: p.name.lower())
             if p.suffix.lower() in IMAGE_EXT | VIDEO_EXT]
    return files


def match_media(title: str, files: list[str], used: set) -> list[str]:
    """Imágenes cuyo nombre contiene el título (o el número) del elemento."""
    t = _norm(title)
    toks = [w for w in t.split() if len(w) > 3]
    hits = []
    for f in files:
        n = _norm(Path(f).stem)
        if f in used:
            continue
        if (t and (t in n or n in t) and len(n) > 2) or (toks and sum(w in n for w in toks) >= max(1, len(toks) // 2 + len(toks) % 2) and len(toks) <= 4):
            hits.append(f)
    return hits


def split_script(text: str, title: str = "", countdown: bool = True, media_dir: str = "", max_words: int = 38,
                 intro: bool = False, top: bool = False) -> dict:
    lines = [l.rstrip() for l in text.replace("\r", "").split("\n")]
    files = list_media(media_dir)
    used: set = set()
    scenes: list[dict] = []
    # --- ¿hay elementos numerados?
    blocks, cur, pre = [], None, []
    for l in lines:
        if not l.strip():
            if cur:
                cur["body"].append("")
            elif pre is not None:
                pre.append("")
            continue
        nb = _numbered(l)
        if nb and len(nb[1]) <= 120:
            cur = {"rank": nb[0], "title": nb[1], "body": []}
            blocks.append(cur)
        elif cur:
            cur["body"].append(l.strip())
        else:
            pre.append(l.strip())
    pre_text = " ".join(x for x in pre if x).strip()
    if top and len(blocks) >= 2:
        nums = [int(b["rank"]) for b in blocks]
        n = len(blocks)
        if intro and (title or pre_text):
            scenes.append({"type": "title", "kicker": f"Top {n}", "title": title or pre_text.split(".")[0][:70],
                           "narration": pre_text or title})
        for b in blocks:
            body = " ".join(x for x in b["body"] if x).strip()
            m = match_media(b["title"], files, used)
            if not m and files and not any(match_media(x["title"], files, set()) for x in blocks):
                m = []
            used.update(m)
            # descripción corta para pantalla; narración completa
            short = (_sentences(body) or [""])[0]
            if len(short) > 110:
                short = short[:107].rsplit(" ", 1)[0] + "…"
            scenes.append({"type": "top_item", "rank": b["rank"], "title": b["title"], "text": short, "media": m,
                           "narration": (b["title"] + ". " + body).strip()})
        # si ningún nombre coincide, reparte las imágenes en orden
        if files and not used:
            items = [s for s in scenes if s["type"] == "top_item"]
            for s, f in zip(items, files):
                s["media"] = [f]
        # orden de cuenta regresiva
        if countdown and nums == sorted(nums):
            pass
    else:
        paras = [p.strip() for p in re.split(r"\n\s*\n", "\n".join(lines)) if p.strip()]
        if not paras:
            return {"settings": {}, "scenes": []}
        chunks = [c for p in paras for c in _chunk(" ".join(p.split()), max_words)]
        for i, c in enumerate(chunks):
            sc = {"type": "broll", "narration": c, "media": []}
            if files:
                sc["media"] = [files[i % len(files)]]
            scenes.append(sc)
    return {"settings": {}, "scenes": scenes}
