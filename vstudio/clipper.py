"""Auto-clipping: transcribe un video largo y propone los mejores fragmentos."""
from __future__ import annotations

import json
import re
import urllib.request

from . import audio as A
from .core import probe_duration

HOOK_WORDS = {
    "es": ["nunca", "secreto", "increíble", "increible", "error", "verdad", "cuidado", "truco", "increíblemente",
           "peligro", "mentira", "descubr", "nadie", "siempre", "locura", "impresionante", "no sabías", "no sabias",
           "por qué", "por que", "cómo", "como", "millones", "primera vez", "jamás", "jamas", "prohibido"],
    "en": ["never", "secret", "incredible", "mistake", "truth", "careful", "trick", "danger", "lie", "discover",
           "nobody", "always", "crazy", "shocking", "why", "how", "million", "first time", "banned"],
}
END_PUNCT = (".", "?", "!", "…", "。")


def _score(segs: list[dict], dur: float, lo: float, hi: float) -> float:
    text = " ".join(s["text"] for s in segs)
    words = len(re.findall(r"\S+", text))
    wps = words / max(dur, 1)
    score = 1.5 - abs(wps - 3.0) * 0.5                      # ritmo del habla ideal ≈ 3 palabras/s
    first = segs[0]["text"].lower()
    low = text.lower()
    if "?" in segs[0]["text"]:
        score += 1.5
    if re.search(r"\d", first):
        score += 0.8
    hooks = sum(1 for w in HOOK_WORDS["es"] + HOOK_WORDS["en"] if w in first)
    hooks_all = sum(1 for w in HOOK_WORDS["es"] + HOOK_WORDS["en"] if w in low)
    score += min(hooks, 3) * 0.9 + min(hooks_all, 6) * 0.25
    score += min(text.count("!"), 3) * 0.3 + min(text.count("?"), 3) * 0.3
    gaps = sum(max(0.0, b["start"] - a["end"] - 1.2) for a, b in zip(segs, segs[1:]))
    score -= gaps * 0.6
    mid = (lo + hi) / 2
    score += 1.0 - abs(dur - mid) / mid
    return score


def propose_heuristic(segments: list[dict], n: int = 5, lo: float = 20, hi: float = 55) -> list[dict]:
    cands = []
    for i in range(len(segments)):
        for j in range(i, len(segments)):
            dur = segments[j]["end"] - segments[i]["start"]
            if dur > hi:
                break
            if dur < lo:
                continue
            ends = segments[j]["text"].rstrip().endswith(END_PUNCT)
            gap = (segments[j + 1]["start"] - segments[j]["end"]) if j + 1 < len(segments) else 9
            if ends or gap > 0.6:
                seg_ = segments[i:j + 1]
                cands.append({"start": segments[i]["start"], "end": segments[j]["end"],
                              "score": _score(seg_, dur, lo, hi),
                              "text": " ".join(s["text"] for s in seg_)})
    cands.sort(key=lambda c: -c["score"])
    chosen: list[dict] = []
    for c in cands:
        if all(c["end"] <= x["start"] or c["start"] >= x["end"] for x in chosen):
            chosen.append(c)
        if len(chosen) >= n:
            break
    chosen.sort(key=lambda c: c["start"])
    for c in chosen:
        first = re.split(r"(?<=[.!?…])\s", c["text"].strip())[0]
        c["title"] = first[:70].rstrip(" ,;:") + ("…" if len(first) > 70 else "")
    return chosen


def propose_gemini(segments: list[dict], n: int, lo: float, hi: float, api_key: str,
                   model: str = "gemini-2.5-flash") -> list[dict]:
    lines = "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments)
    prompt = (f"Eres editor de videos virales verticales. De esta transcripción con tiempos (segundos) elige los {n} "
              f"mejores fragmentos independientes, de {lo:.0f} a {hi:.0f} s cada uno, que empiecen con un gancho "
              "fuerte y terminen en una idea completa. Responde SOLO JSON: "
              '[{"start":0.0,"end":0.0,"title":"gancho corto"}].\n\n' + lines[:60000])
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"responseMimeType": "application/json"}}).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        res = json.loads(r.read().decode())
    txt = res["candidates"][0]["content"]["parts"][0]["text"]
    out = []
    for c in json.loads(txt):
        s, e = float(c["start"]), float(c["end"])
        if e - s >= 5:
            out.append({"start": s, "end": e, "score": 0, "title": str(c.get("title", "")), "text": ""})
    return out[:n]


def analyze(video: str, n: int = 5, lo: float = 20, hi: float = 55, model: str = "small",
            language: str | None = None, gemini_key: str | None = None, progress=None) -> list[dict]:
    if not A.whisper_available():
        raise RuntimeError("Para el auto-clipping instala faster-whisper:  pip install faster-whisper")
    segs = A.transcribe(video, model, language or None, progress=progress)
    if not segs:
        raise RuntimeError("No se detectó voz en el video.")
    if gemini_key:
        try:
            clips = propose_gemini(segs, n, lo, hi, gemini_key)
            if clips:
                return clips
        except Exception:
            pass  # cae a la heurística local
    return propose_heuristic(segs, n, lo, hi)


def to_scenes(video: str, clips: list[dict], fit: str = "blur", hooks: bool = True) -> list[dict]:
    return [{"type": "clip", "source": video, "start": round(c["start"], 2), "end": round(c["end"], 2),
             "fit": fit, "hook": c.get("title", "") if hooks else "", "captions": True} for c in clips]
