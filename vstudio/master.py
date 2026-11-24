"""Voz maestra: todo el guion de un tramo se sintetiza en UNA sola llamada (misma entonación y ritmo) y se corta por escenas.

Los cortes se buscan en las pausas del audio más cercanas al punto donde, por el texto, termina cada escena.
"""
import os
import re
import wave

import numpy as np

from . import audio as A
from . import voices as V
from .core import CACHE_DIR, hash_key, ffmpeg_bin, run_quiet, probe_duration

MAX_CHARS = 3000          # límite por llamada (el modelo admite ~8k tokens de entrada)
FRAME = 0.01              # s por ventana de energía


def _load(path):
    with wave.open(str(path), "rb") as w:
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        x = np.frombuffer(w.readframes(n), np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(1)
    return x, sr


def energy(path):
    """(energía por ventana de 10 ms, umbral de silencio)."""
    x, sr = _load(path)
    k = max(1, int(sr * FRAME))
    n = len(x) // k
    e = np.sqrt((x[:n * k].reshape(n, k) ** 2).mean(1)) if n else np.zeros(1)
    peak = float(np.percentile(e, 98)) if len(e) else 0.0
    return e, max(0.004, peak * 0.06)


def validate(path, text, min_wps=1.0, max_wps=6.5):
    """Comprueba que el audio exista, tenga voz y una duración coherente con el texto. Devuelve (ok, motivo)."""
    if not os.path.isfile(path):
        return False, "no se creó el archivo"
    dur = probe_duration(path)
    words = len(re.findall(r"\S+", text))
    if dur <= 0.3:
        return False, "audio vacío"
    if words >= 4 and not (min_wps <= words / dur <= max_wps):
        return False, f"duración rara ({words} palabras en {dur:.1f}s)"
    try:
        e, thr = energy(path)
        if (e > thr).mean() < 0.15:
            return False, "casi todo es silencio"
    except Exception:
        pass
    return True, ""


def _gaps(e, thr, min_len=0.12):
    sil = e <= thr
    out, i, n = [], 0, len(sil)
    while i < n:
        if sil[i]:
            j = i
            while j < n and sil[j]:
                j += 1
            if (j - i) * FRAME >= min_len:
                out.append((i * FRAME, j * FRAME))
            i = j
        else:
            i += 1
    return out


def boundaries(texts, path):
    """Instantes de corte entre escenas (len(texts)-1) sobre un audio continuo."""
    dur = probe_duration(path)
    e, thr = energy(path)
    gaps = _gaps(e, thr)
    full = " ".join(texts)
    est = A.estimate_words(full, dur)
    cuts, i = [], 0
    for k, t in enumerate(texts[:-1]):
        i += len(re.findall(r"\S+", t))
        exp = (est[i - 1][2] + est[i][1]) / 2 if 0 < i < len(est) else dur * i / max(1, len(est))
        best, score = None, 1e9
        for a, b in gaps:
            c = (a + b) / 2
            if cuts and c <= cuts[-1] + 0.4:
                continue
            sc = abs(c - exp) - 0.6 * (b - a)       # cerca del punto esperado y preferir pausas largas
            if abs(c - exp) <= 1.5 and sc < score:
                best, score = c, sc
        cuts.append(best if best is not None else max(exp, (cuts[-1] + 0.5) if cuts else 0.5))
    return cuts


def _cuts_from_words(aw, texts, e, thr, dur):
    """Cortes entre escenas usando los tiempos reales: la pausa más larga entre la última palabra de una escena y la primera de la siguiente."""
    gaps = _gaps(e, thr, 0.08)
    cuts, i = [], 0
    for t in texts[:-1]:
        i += len(re.findall(r"\S+", t))
        a_end, b_start = aw[i - 1][2], aw[i][1]
        mid = (a_end + b_start) / 2
        best, bl = None, 0.0
        for g0, g1 in gaps:
            if g1 >= a_end - 0.05 and g0 <= b_start + 0.05 and (g1 - g0) > bl:
                best, bl = (g0 + g1) / 2, g1 - g0
        c = best if best is not None else mid
        c = min(max(c, a_end), max(a_end, b_start)) if b_start > a_end else (a_end + b_start) / 2
        cuts.append(max(c, (cuts[-1] + 0.3) if cuts else 0.3))
    return cuts


def _slice(src, t0, t1, dst):
    run_quiet([ffmpeg_bin(), "-y", "-v", "error", "-ss", f"{t0:.3f}", "-to", f"{t1:.3f}", "-i", str(src),
               "-ac", "1", "-ar", "24000", str(dst)])


def synth_validated(text, vz, tries=3):
    last = ""
    for k in range(tries):
        path, _w, _d = A.synthesize(text, vz["engine"], vz["voice"] or A.DEFAULT_VOICE_ES, vz["rate"], vz["model"], vz["style"])
        ok, why = validate(path, text) if path else (True, "")
        if ok:
            return path
        last = why
        for ext in ("", ):                    # descarta la caché mala y reintenta
            try:
                os.remove(path)
                os.remove(os.path.splitext(path)[0] + ".json")
            except OSError:
                pass
    raise RuntimeError(f"Gemini no devolvió un audio válido tras {tries} intentos: {last}")


def plan(specs, settings, types, warn=None):
    """{índice_escena: (ruta_audio, palabras, duración)} para las escenas que se narran con voz maestra."""
    if not settings.get("master_audio", True):
        return {}
    items = []
    for i, s in enumerate(specs):
        narr = (s.get("narration") or "").strip()
        if not narr or s.get("audio"):
            continue
        vz = V.resolve(s, settings, types[i], warn=warn)
        if vz["engine"] != "gemini":
            continue
        items.append((i, narr, vz))
    out, group = {}, []

    def flush():
        if not group:
            return
        texts = [g[1] for g in group]
        vz = group[0][2]
        full = "\n".join(texts)
        path = synth_validated(full, vz)
        dur = probe_duration(path)
        e, thr = energy(path)
        aw = A.aligned_words(path, " ".join(texts), dur)      # tiempos reales con Whisper (None = se estiman)
        cuts = _cuts_from_words(aw, texts, e, thr, dur) if aw else boundaries(texts, path)
        pos = 0
        edges = [0.0] + cuts + [dur]
        tdir = CACHE_DIR / "tts"
        for k, (idx, narr, _vz) in enumerate(group):
            dst = tdir / (hash_key("master", os.path.basename(path), k, round(edges[k], 2), round(edges[k + 1], 2)) + ".wav")
            if not dst.exists():
                _slice(path, edges[k], edges[k + 1], dst)
            tt = dst.with_suffix(".tt")
            if not tt.exists():                       # quita el ruido final (una sola vez, también en audios ya guardados)
                A.trim_tail(str(dst))
                tt.write_text("1")
            d = probe_duration(dst)
            ntok = len(re.findall(r"\S+", narr))
            if aw:
                ws = [(w, round(max(0.0, s0 - edges[k]), 3), round(min(d, max(s0 - edges[k] + 0.06, e0 - edges[k])), 3))
                      for (w, s0, e0) in aw[pos:pos + ntok]]
                pos += ntok
                out[idx] = (str(dst), ws, d)
                continue
            a, b = int(edges[k] / FRAME), min(len(e), int(edges[k + 1] / FRAME))
            voiced = np.where(e[a:b] > thr)[0]
            lead = float(voiced[0] * FRAME) if len(voiced) else 0.15
            tail = float((b - a - voiced[-1]) * FRAME) if len(voiced) else 0.25
            out[idx] = (str(dst), A.estimate_words(narr, d, 0.0, max(0.05, lead), max(0.1, tail)), d)
        group.clear()

    n = 0
    for it in items:
        same = group and group[0][2] == it[2]
        if group and (not same or n + len(it[1]) > MAX_CHARS):
            flush()
            n = 0
        group.append(it)
        n += len(it[1]) + 1
    flush()
    return out
