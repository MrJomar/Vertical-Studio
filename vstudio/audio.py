"""Voz (TTS), tiempos por palabra y transcripción con Whisper."""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

from .core import CACHE_DIR, hash_key, probe_duration, run_quiet, ffmpeg_bin

Words = list  # [(texto, inicio, fin), ...]

DEFAULT_VOICE_ES = "es-MX-JorgeNeural"


def estimate_words(text: str, duration: float, start: float = 0.0, lead: float = 0.15, tail: float = 0.25) -> Words:
    """Reparte las palabras en el tiempo proporcional a su longitud (cuando no hay tiempos reales)."""
    toks = re.findall(r"\S+", text or "")
    if not toks:
        return []
    avail = max(0.2, duration - lead - tail)
    weights = []
    for tk in toks:
        w = len(tk) + 2.0
        if tk[-1] in ".!?…":
            w += 4
        elif tk[-1] in ",;:":
            w += 2
        weights.append(w)
    total = sum(weights)
    out, t = [], start + lead
    for tk, w in zip(toks, weights):
        d = avail * w / total
        out.append((tk, t, t + d))
        t += d
    return out


def estimate_duration(text: str, wpm: float = 165.0) -> float:
    n = len(re.findall(r"\S+", text or ""))
    return max(1.0, n * 60.0 / wpm)


# --------------------------------------------------------------------------- TTS
async def _edge_async(text: str, voice: str, rate: str, out: str):
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words = []
    with open(out, "wb") as f:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                s = ch["offset"] / 1e7
                d = ch["duration"] / 1e7
                words.append((ch["text"], s, s + d))
    return words


def synthesize(text: str, engine: str = "edge", voice: str = DEFAULT_VOICE_ES, rate: int = 0
               ) -> tuple[str | None, Words, float]:
    """Devuelve (ruta_audio|None, palabras, duración). Cachea por texto/voz."""
    text = (text or "").strip()
    if not text:
        return None, [], 0.0
    engine = (engine or "edge").lower()
    if engine in ("silencio", "none", "ninguno"):
        d = estimate_duration(text)
        return None, estimate_words(text, d), d
    tdir = CACHE_DIR / "tts"
    tdir.mkdir(parents=True, exist_ok=True)
    key = hash_key(engine, voice, rate, text)
    ext = ".mp3" if engine == "edge" else ".wav"
    audio, meta = tdir / (key + ext), tdir / (key + ".json")
    if audio.exists() and meta.exists():
        try:
            words = [tuple(w) for w in json.loads(meta.read_text("utf-8"))]
            return str(audio), words, probe_duration(audio)
        except Exception:
            pass
    words: Words = []
    if engine == "edge":
        words = asyncio.run(_edge_async(text, voice or DEFAULT_VOICE_ES, f"{int(rate):+d}%", str(audio)))
    elif engine in ("sapi", "pyttsx3", "offline"):
        import pyttsx3
        eng = pyttsx3.init()
        if voice:
            for v in eng.getProperty("voices"):
                if voice.lower() in (v.name or "").lower() or voice.lower() in (v.id or "").lower():
                    eng.setProperty("voice", v.id)
                    break
        eng.setProperty("rate", int(175 + rate * 1.5))
        eng.save_to_file(text, str(audio))
        eng.runAndWait()
    else:
        raise ValueError(f"Motor de voz desconocido: {engine}")
    dur = probe_duration(audio)
    if dur <= 0:
        raise RuntimeError("No se generó audio de voz (revisa tu conexión o el motor de voz).")
    if not words:
        words = estimate_words(text, dur)
    meta.write_text(json.dumps(words), "utf-8")
    return str(audio), words, dur


# --------------------------------------------------------------------------- Whisper
_models: dict = {}


def whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def _get_model(size: str):
    if size in _models:
        return _models[size]
    from faster_whisper import WhisperModel
    device, ctype = "cpu", "int8"
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            device, ctype = "cuda", "float16"
    except Exception:
        pass
    try:
        m = WhisperModel(size, device=device, compute_type=ctype)
    except Exception:
        m = WhisperModel(size, device="cpu", compute_type="int8")
    _models[size] = m
    return m


def transcribe(path: str, size: str = "small", language: str | None = None,
               start: float = 0.0, end: float | None = None, progress=None) -> list[dict]:
    """Segmentos con palabras: [{start,end,text,words:[(w,s,e)]}] (tiempos relativos al inicio del archivo)."""
    st = os.stat(path)
    key = hash_key(path, st.st_size, int(st.st_mtime), size, language, start, end)
    cdir = CACHE_DIR / "asr"
    cdir.mkdir(parents=True, exist_ok=True)
    cfile = cdir / (key + ".json")
    if cfile.exists():
        try:
            return json.loads(cfile.read_text("utf-8"))
        except Exception:
            pass
    src = path
    if start > 0 or end is not None:  # recorta solo el audio necesario
        tmp = cdir / (key + ".wav")
        cmd = [ffmpeg_bin(), "-y", "-v", "error", "-ss", f"{start:.3f}"]
        if end is not None:
            cmd += ["-t", f"{end - start:.3f}"]
        cmd += ["-i", path, "-vn", "-ac", "1", "-ar", "16000", str(tmp)]
        run_quiet(cmd)
        src = str(tmp)
    model = _get_model(size)
    segs_iter, info = model.transcribe(src, language=language, word_timestamps=True, vad_filter=True,
                                       beam_size=1 if size in ("tiny", "base") else 3)
    total = float(getattr(info, "duration", 0) or 0)
    out = []
    for s in segs_iter:
        words = [(w.word.strip(), float(w.start), float(w.end)) for w in (s.words or []) if w.word.strip()]
        out.append({"start": float(s.start), "end": float(s.end), "text": s.text.strip(), "words": words})
        if progress and total:
            progress(min(1.0, float(s.end) / total))
    cfile.write_text(json.dumps(out), "utf-8")
    return out
