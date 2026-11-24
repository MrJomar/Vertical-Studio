"""Efectos de sonido: banco generado por código (+ tus propios archivos), análisis local y planificación de eventos.

- assets/sfx/*.wav  → sonidos incluidos (se generan solos la primera vez) y los que tú agregues (wav/mp3/ogg/m4a/flac).
- Cada archivo se analiza: duración, volumen real, instante del «golpe» (pico) y brillo. Con eso se nivela el volumen y
  se alinea el golpe con el momento exacto de la animación.
- La etiqueta (tag) sale del nombre: «whoosh_2.wav» → whoosh, «impacto.mp3» → impacto, o de la subcarpeta.
- Ajustes del proyecto: "sfx": "off" | "manual" (solo los de las escenas) | "auto" (además automáticos); "sfx_volume": 0-1.
- En una escena: "sfx": "pop"  |  ["impacto@0.8", "click@2.1"]  |  [{"tag":"splash","at":1.2,"vol":0.8}]
"""
from __future__ import annotations

import json
import math
import wave
from pathlib import Path

import numpy as np

from .core import APP_DIR, ffmpeg_bin, run_quiet

SFX_DIR = APP_DIR / "assets" / "sfx"
SR = 44100
AUDIO_EXT = (".wav", ".mp3", ".ogg", ".m4a", ".flac")

# ¿para qué sirve cada etiqueta? (lo lee la IA diaria y el revisor)
USOS = {
    "whoosh": "transición entre escenas, cámara que se mueve rápido",
    "whoosh_corto": "cambios de plano rápidos, elementos que cruzan la pantalla",
    "pop": "aparece una pieza o elemento",
    "click": "aparece un texto, un pin o un detalle pequeño",
    "splash": "agua, líquido, golpe de color",
    "impacto": "susto, dato fuerte, golpe dramático",
    "tic": "reloj, cuenta atrás, tensión",
    "ding": "acierto, dato clave, aviso",
    "subida": "tensión que crece antes de una revelación",
}
ALIAS = {"swoosh": "whoosh", "woosh": "whoosh", "transicion": "whoosh", "hit": "impacto", "boom": "impacto",
         "clic": "click", "tick": "tic", "bell": "ding", "riser": "subida", "bubble": "pop", "aparece": "pop"}


# --------------------------------------------------------------------------- generación
def _env_exp(n, tau):
    return np.exp(-np.arange(n) / (tau * SR))


def _band_noise(n, f0, f1, rng, q=1.0):
    """Ruido pasa-banda cuyo centro barre de f0 a f1 (filtros de un polo en cascada)."""
    x = rng.standard_normal(n)
    fc = np.geomspace(max(f0, 20), max(f1, 20), n)
    a = np.clip(2 * np.pi * fc / SR, 0, 0.95)
    lo = np.empty(n)
    hi = np.empty(n)
    y1 = y2 = 0.0
    for i in range(n):
        y1 += a[i] * (x[i] - y1)
        y2 += a[i] * 0.35 * (x[i] - y2)
        lo[i], hi[i] = y1, y2
    return (lo - hi) * (1 + q)


def _norm(x, peak=0.9):
    m = np.max(np.abs(x)) or 1.0
    return (x / m * peak).astype(np.float32)


def _gen(name: str) -> np.ndarray:
    rng = np.random.default_rng(sum(map(ord, name)))
    if name in ("whoosh", "whoosh_corto"):
        d = 0.75 if name == "whoosh" else 0.38
        n = int(d * SR)
        t = np.linspace(0, 1, n)
        env = np.sin(np.pi * np.clip(t, 0, 1) ** 1.6) ** 2          # sube y baja; pico hacia 0.6
        x = _band_noise(n, 300, 5200, rng) * env
        return _norm(x)
    if name == "pop":
        n = int(0.16 * SR)
        t = np.arange(n) / SR
        f = 150 + 650 * np.exp(-t * 38)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env_exp(n, 0.035)
        x[:60] += rng.standard_normal(60) * 0.25 * np.linspace(1, 0, 60)
        return _norm(x)
    if name == "click":
        n = int(0.06 * SR)
        t = np.arange(n) / SR
        x = np.sin(2 * np.pi * 2600 * t) * _env_exp(n, 0.006)
        x[:90] += rng.standard_normal(90) * 0.5 * np.linspace(1, 0, 90)
        return _norm(x)
    if name == "splash":
        n = int(0.8 * SR)
        x = _band_noise(n, 6000, 1800, rng) * (_env_exp(n, 0.16) * (1 - np.exp(-np.arange(n) / (0.004 * SR))))
        for k in range(5):                                             # burbujas
            s = int((0.06 + 0.11 * k + rng.uniform(0, 0.05)) * SR)
            m = int(0.07 * SR)
            if s + m < n:
                tt = np.arange(m) / SR
                f = rng.uniform(500, 1100) * (1 + 4 * tt * 8)
                x[s:s + m] += 0.35 * np.sin(2 * np.pi * np.cumsum(f) / SR) * _env_exp(m, 0.02)
        return _norm(x)
    if name == "impacto":
        n = int(1.1 * SR)
        t = np.arange(n) / SR
        f = 34 + 70 * np.exp(-t * 14)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env_exp(n, 0.35)
        nz = _band_noise(int(0.25 * SR), 80, 600, rng) * _env_exp(int(0.25 * SR), 0.05)
        x[:len(nz)] += nz * 0.9
        return _norm(np.tanh(x * 1.6))
    if name == "tic":
        n = int(0.09 * SR)
        t = np.arange(n) / SR
        x = np.sin(2 * np.pi * 1700 * t) * _env_exp(n, 0.012) + 0.4 * np.sin(2 * np.pi * 3400 * t) * _env_exp(n, 0.006)
        return _norm(x)
    if name == "ding":
        n = int(1.0 * SR)
        t = np.arange(n) / SR
        x = sum(a * np.sin(2 * np.pi * f * t) * _env_exp(n, tau) for a, f, tau in
                ((1, 1320, 0.30), (0.4, 2640, 0.15), (0.2, 3960, 0.08)))
        x[:40] *= np.linspace(0, 1, 40)
        return _norm(x)
    if name == "subida":
        n = int(1.6 * SR)
        t = np.linspace(0, 1, n)
        x = _band_noise(n, 200, 6000, rng) * (t ** 2.2)
        x += 0.25 * np.sin(2 * np.pi * np.cumsum(90 + 700 * t ** 3) / SR) * t ** 2
        x[-int(0.04 * SR):] *= np.linspace(1, 0, int(0.04 * SR))
        return _norm(x)
    raise KeyError(name)


def _write_wav(path: Path, x: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def ensure_bank() -> None:
    """Crea los sonidos incluidos que falten (si ya existe un archivo con ese nombre, se respeta el tuyo)."""
    for name in USOS:
        f = SFX_DIR / f"{name}.wav"
        if not f.exists() and not any(p.stem == name for p in SFX_DIR.glob("*") if p.suffix.lower() in AUDIO_EXT):
            _write_wav(f, _gen(name))


# --------------------------------------------------------------------------- análisis
def _load(path: Path) -> np.ndarray:
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path)) as w:
                if w.getsampwidth() == 2 and w.getframerate() == SR:
                    a = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768
                    return a.reshape(-1, w.getnchannels()).mean(axis=1)
        except Exception:
            pass
    r = run_quiet([ffmpeg_bin(), "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"])
    return np.frombuffer(r.stdout, "<f4").copy() if r.returncode == 0 else np.zeros(0, np.float32)


def tag_of(path: Path) -> str:
    base = path.stem.lower()
    while base and (base[-1].isdigit() or base[-1] in "_- "):
        base = base[:-1]
    base = base or path.stem.lower()
    if base not in USOS and base not in ALIAS and path.parent != SFX_DIR:
        base = path.parent.name.lower()
    return ALIAS.get(base, base)


def analyze(path: Path) -> dict | None:
    x = _load(path)
    if len(x) < 200:
        return None
    ab = np.abs(x)
    thr = ab.max() * 0.02
    nz = np.where(ab > thr)[0]
    a, b = (int(nz[0]), int(nz[-1]) + 1) if len(nz) else (0, len(x))
    x = x[a:b]
    k = max(1, int(0.005 * SR))
    env = np.convolve(np.abs(x), np.ones(k) / k, "same")
    hit = float(np.argmax(env)) / SR
    rms = float(np.sqrt(np.mean(x ** 2)) + 1e-9)
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    fr = np.fft.rfftfreq(len(x), 1 / SR)
    cen = float((spec * fr).sum() / (spec.sum() + 1e-9))
    return {"dur": round(len(x) / SR, 3), "hit": round(hit, 3), "rms_db": round(20 * math.log10(rms), 1),
            "peak_db": round(20 * math.log10(float(np.abs(x).max()) + 1e-9), 1),
            "brillo": "agudo" if cen > 2500 else "medio" if cen > 900 else "grave",
            "trim": round(a / SR, 3)}


def build_catalog(force: bool = False) -> dict:
    """Escanea assets/sfx, analiza lo nuevo y guarda catalogo.json. Devuelve {nombre: info}."""
    ensure_bank()
    cf = SFX_DIR / "catalogo.json"
    old = {}
    if cf.exists() and not force:
        try:
            old = json.loads(cf.read_text("utf-8"))
        except Exception:
            old = {}
    cat = {}
    for p in sorted(SFX_DIR.rglob("*")):
        if p.suffix.lower() not in AUDIO_EXT:
            continue
        rel = p.relative_to(SFX_DIR).as_posix()
        mt = int(p.stat().st_mtime)
        o = old.get(rel)
        if o and o.get("mtime") == mt:
            cat[rel] = o
            continue
        info = analyze(p)
        if info:
            t = tag_of(p)
            cat[rel] = {"tag": t, "uso": USOS.get(t, ""), "mtime": mt, **info}
    cf.write_text(json.dumps(cat, ensure_ascii=False, indent=1), "utf-8")
    return cat


def catalog_md() -> str:
    cat = build_catalog()
    tags: dict = {}
    for rel, i in cat.items():
        tags.setdefault(i["tag"], []).append((rel, i))
    out = ["# Efectos de sonido disponibles", "", "Usa la etiqueta en `\"sfx\"` de la escena (ej.: `\"sfx\": [\"impacto@0.8\"]`).", ""]
    for t, lst in sorted(tags.items()):
        out.append(f"- **{t}** — {USOS.get(t, 'sin descripción')} ({len(lst)} archivo{'s' if len(lst) > 1 else ''}, "
                   f"{lst[0][1]['dur']} s, {lst[0][1]['brillo']})")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- planificación
def _parse(ev, scene_dur):
    """Un elemento de «sfx» de una escena → (tag, t_en_escena, vol) o None."""
    if isinstance(ev, str):
        tag, _, t = ev.partition("@")
        try:
            return tag.strip().lower(), (float(t) if t else 0.0), 1.0
        except ValueError:
            return None
    if isinstance(ev, dict):
        tag = str(ev.get("tag") or ev.get("name") or "").lower()
        try:
            return tag, float(ev.get("at", 0.0)), float(ev.get("vol", 1.0))
        except (TypeError, ValueError):
            return None
    return None


def plan_events(scenes, starts, settings, tlen_s) -> tuple[list[tuple[float, str, float]], list[str]]:
    """Devuelve ([(t_global, tag, vol_rel)], avisos). starts[i] = inicio global (s) de la escena i."""
    mode = str(settings.get("sfx", "manual") or "off").lower()
    warns: list[str] = []
    if mode == "off":
        return [], warns
    ev: list[tuple[float, str, float, bool]] = []     # (t, tag, vol, manual)
    for i, sc in enumerate(scenes):
        t0 = starts[i]
        raw = sc.spec.get("sfx")
        if raw not in (None, "", False):
            for e in (raw if isinstance(raw, list) else [raw]):
                p = _parse(e, sc.duration)
                if p and p[0]:
                    ev.append((t0 + max(0.0, p[1]), p[0], p[2], True))
                else:
                    warns.append(f"Escena {i + 1}: efecto de sonido no entendido: {e!r}")
        if mode == "auto":
            if i > 0 and getattr(sc, "transition", "cut") != "cut" and tlen_s > 0:
                ev.append((t0 + tlen_s * 0.5, "whoosh", 1.0, False))
            if sc.spec.get("sfx_auto", True):
                try:
                    for t, tag in sc.sfx_events():
                        ev.append((t0 + t, tag, 1.0, False))
                except Exception:
                    pass
    ev.sort(key=lambda e: e[0])
    out: list[tuple[float, str, float]] = []
    last_any = -9.0
    last_tag: dict = {}
    for t, tag, vol, manual in ev:
        if not manual and (t - last_any < 0.22 or t - last_tag.get(tag, -9) < 0.6):
            continue                                   # automáticos: nunca amontonados
        out.append((t, tag, vol))
        last_any = t
        last_tag[tag] = t
    return out, warns


def resolve_tracks(events, settings, total) -> tuple[list[tuple[str, float, float]], list[str]]:
    """Eventos → pistas (archivo, inicio_s, volumen) con volumen nivelado y golpe alineado."""
    cat = build_catalog()
    by_tag: dict = {}
    for rel, i in cat.items():
        by_tag.setdefault(i["tag"], []).append((rel, i))
    vol_set = max(0.0, min(1.0, float(settings.get("sfx_volume", 0.5) or 0.0)))
    target = -30.0 + 20 * math.log10(max(vol_set, 1e-3) / 0.5)    # rms objetivo (dBFS); la voz ronda -20
    warns: list[str] = []
    tracks = []
    n_used: dict = {}
    for t, tag, rel_vol in events:
        tag = ALIAS.get(tag, tag)
        lst = by_tag.get(tag)
        if not lst:
            warns.append(f"No hay efecto de sonido «{tag}» (disponibles: {', '.join(sorted(by_tag))}).")
            continue
        k = n_used.get(tag, 0)
        n_used[tag] = k + 1
        rel, info = lst[k % len(lst)]
        jitter = ((k * 37) % 7 - 3) * 0.35                      # ±1 dB de variación determinista
        gain_db = target - info["rms_db"] + jitter
        gain_db = min(gain_db, -1.5 - info["peak_db"])          # nunca saturar
        gain = 10 ** (gain_db / 20) * rel_vol
        start = t - info["hit"] - info.get("trim", 0.0)
        tracks.append((str(SFX_DIR / rel), max(0.0, start), gain))
    return [x for x in tracks if x[1] < total], warns
