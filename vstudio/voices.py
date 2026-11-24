"""Voces: perfiles, clave de Gemini, catálogos de voces y modelos de audio."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

from .core import CACHE_DIR

FILE = CACHE_DIR / "voices.json"
EDGE_CACHE = CACHE_DIR / "edge_voices.json"

# Modelos de audio (TTS) de Gemini. Con una clave válida se consulta la lista real y se filtran solo los de audio.
GEMINI_MODELS = ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "gemini-3.1-flash-tts-preview",
                 "gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"]
DEFAULT_GEMINI_MODEL = GEMINI_MODELS[0]

GEMINI_VOICES = [
    ("Zephyr", "Brillante"), ("Puck", "Animada"), ("Charon", "Informativa"), ("Kore", "Firme"), ("Fenrir", "Emocionada"),
    ("Leda", "Juvenil"), ("Orus", "Firme"), ("Aoede", "Ligera"), ("Callirrhoe", "Relajada"), ("Autonoe", "Brillante"),
    ("Enceladus", "Susurrante"), ("Iapetus", "Clara"), ("Umbriel", "Relajada"), ("Algieba", "Suave"), ("Despina", "Suave"),
    ("Erinome", "Clara"), ("Algenib", "Rasposa"), ("Rasalgethi", "Informativa"), ("Laomedeia", "Animada"),
    ("Achernar", "Suave"), ("Alnilam", "Firme"), ("Schedar", "Uniforme"), ("Gacrux", "Madura"), ("Pulcherrima", "Directa"),
    ("Achird", "Amistosa"), ("Zubenelgenubi", "Casual"), ("Vindemiatrix", "Gentil"), ("Sadachbia", "Vivaz"),
    ("Sadaltager", "Experta"), ("Sulafat", "Cálida")]

TYPES = ["map", "vector", "broll", "clip"]
IMG_MODEL_DEFAULT = "gemini-2.5-pro"
_DEFAULT = {"gemini_key": "", "gemini_model": DEFAULT_GEMINI_MODEL, "img_key": "", "img_model": IMG_MODEL_DEFAULT, "profiles": {}, "type_defaults": {}}


def load() -> dict:
    try:
        d = json.loads(FILE.read_text("utf-8"))
    except Exception:
        d = {}
    return {**_DEFAULT, **d}


def save(d: dict) -> dict:
    cur = load()
    cur.update({k: d[k] for k in _DEFAULT if k in d})
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=2), "utf-8")
    return cur


def public() -> dict:
    """Configuración sin exponer la clave."""
    d = load()
    key = d.pop("gemini_key", "")
    d["has_key"] = bool(key)
    d["key_hint"] = ("…" + key[-4:]) if key else ""
    ik = d.pop("img_key", "")
    d["has_img_key"] = bool(ik)
    d["img_key_hint"] = ("…" + ik[-4:]) if ik else ""
    d["img_model"] = d.get("img_model") or IMG_MODEL_DEFAULT
    return d


def get_key() -> str:
    return load().get("gemini_key", "")


def get_img_key() -> str:
    """Clave para generar piezas/imágenes; si no hay una propia se usa la de la voz."""
    d = load()
    return d.get("img_key") or d.get("gemini_key", "")


def list_text_models(key: str) -> list[str]:
    """Modelos de texto/código que tu clave puede usar con generateContent (los que sirven para dibujar SVG)."""
    import urllib.request as ur
    out, tok = [], ""
    for _ in range(5):
        url = f"https://generativelanguage.googleapis.com/v1beta/models?pageSize=100&key={key}" + (f"&pageToken={tok}" if tok else "")
        with ur.urlopen(ur.Request(url), timeout=40) as r:
            data = json.loads(r.read().decode())
        for m in data.get("models", []):
            n = m.get("name", "").split("/")[-1]
            if "generateContent" in m.get("supportedGenerationMethods", []) and n.startswith("gemini") \
                    and not any(x in n for x in ("tts", "live", "image", "audio", "embed", "transcribe", "omni", "translate", "robotics", "computer")):
                out.append(n)
        tok = data.get("nextPageToken", "")
        if not tok:
            break
    # los «pro» primero (dibujan mejor), luego flash; lo más nuevo antes
    return sorted(set(out), key=lambda n: (0 if "pro" in n else 1 if "flash" in n and "lite" not in n else 2, n), reverse=False)


def save_profile(name: str, prof: dict) -> dict:
    name = re.sub(r"\s+", " ", str(name)).strip()[:40]
    if not name:
        raise ValueError("Ponle nombre al perfil.")
    d = load()
    keep = ("engine", "voice", "model", "style", "rate")
    d["profiles"][name] = {k: prof.get(k, "") for k in keep}
    return save(d)


def delete_profile(name: str) -> dict:
    d = load()
    d["profiles"].pop(name, None)
    d["type_defaults"] = {k: v for k, v in d["type_defaults"].items() if v != name}
    FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), "utf-8")
    return d


def resolve(spec: dict, settings: dict, scene_type: str, warn=None) -> dict:
    """Voz final de una escena: perfil de la escena > voz explícita > perfil del proyecto > perfil por tipo > ajustes."""
    if settings.get("tts_engine") in ("silencio", "none", "ninguno"):   # vista previa / proyecto mudo: nunca llama a ninguna voz
        return {"engine": "silencio", "voice": "", "model": "", "style": "", "rate": 0}
    cfg = load()
    profs = cfg["profiles"]

    def from_profile(name):
        p = profs.get(name)
        if p is None:
            if warn:
                warn(f"No existe el perfil de voz «{name}» en este equipo; usé la voz de los ajustes.")
            return None
        return {"engine": p.get("engine") or "edge", "voice": p.get("voice") or "", "model": p.get("model") or "",
                "style": p.get("style") or "", "rate": int(p.get("rate") or 0)}

    for name in (spec.get("voice_profile"),):
        if name and (r := from_profile(name)):
            return r
    if spec.get("tts_engine") or spec.get("voice"):
        return {"engine": spec.get("tts_engine") or settings.get("tts_engine", "edge"),
                "voice": spec.get("voice") or settings.get("voice", ""), "model": spec.get("voice_model") or settings.get("voice_model", ""),
                "style": spec.get("voice_style") or settings.get("voice_style", ""),
                "rate": int(spec.get("rate", settings.get("tts_rate", 0)))}
    for name in (settings.get("voice_profile"), cfg["type_defaults"].get(scene_type)):
        if name and (r := from_profile(name)):
            return r
    return {"engine": settings.get("tts_engine", "edge"), "voice": settings.get("voice", ""),
            "model": settings.get("voice_model", ""), "style": settings.get("voice_style", ""),
            "rate": int(settings.get("tts_rate", 0))}


# ------------------------------------------------------------------ catálogos
def edge_voices(refresh: bool = False) -> list:
    """Voces de Edge (necesita internet la primera vez; luego queda en caché)."""
    if not refresh and EDGE_CACHE.exists():
        try:
            return json.loads(EDGE_CACHE.read_text("utf-8"))
        except Exception:
            pass
    try:
        import asyncio
        import edge_tts
        raw = asyncio.run(asyncio.wait_for(edge_tts.list_voices(), 6))
        out = [{"id": v["ShortName"], "label": f'{v["ShortName"]} · {v.get("Gender", "")}', "locale": v.get("Locale", ""),
                "gender": v.get("Gender", "")} for v in raw]
        out.sort(key=lambda v: (not v["locale"].startswith("es"), v["locale"], v["id"]))
        EDGE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        EDGE_CACHE.write_text(json.dumps(out, ensure_ascii=False), "utf-8")
        return out
    except Exception:
        base = ["es-MX-JorgeNeural", "es-MX-DaliaNeural", "es-ES-AlvaroNeural", "es-ES-ElviraNeural", "es-AR-TomasNeural",
                "es-CO-GonzaloNeural", "es-US-AlonsoNeural", "es-CL-LorenzoNeural", "en-US-GuyNeural", "en-US-JennyNeural"]
        return [{"id": v, "label": v, "locale": v[:5], "gender": ""} for v in base]


def sapi_voices() -> list:
    try:
        import pyttsx3
        return [{"id": v.name, "label": v.name, "locale": "", "gender": ""} for v in pyttsx3.init().getProperty("voices")]
    except Exception:
        return []


def list_voices(engine: str) -> list:
    if engine == "gemini":
        return [{"id": n, "label": f"{n} · {d}", "locale": "", "gender": d} for n, d in GEMINI_VOICES]
    if engine == "sapi":
        return sapi_voices()
    if engine == "edge":
        return edge_voices()
    return []


def gemini_models() -> dict:
    """Modelos de audio. Si hay clave, se consulta la API y se dejan solo los que son TTS."""
    key = get_key()
    names = list(GEMINI_MODELS)
    live = False
    if key:
        try:
            req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                                         headers={"x-goog-api-key": key})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            found = [m["name"].split("/")[-1] for m in data.get("models", []) if "tts" in m["name"].lower()]
            if found:
                names, live = sorted(set(found), reverse=True), True
        except Exception:
            pass
    return {"models": names, "live": live}


def style_prompt(style: str, text: str) -> str:
    """Estilo TAL COMO LO ESCRIBIÓ el usuario, seguido del texto (forma de la doc de Google: «Say cheerfully: Have a wonderful day!»).
    No se añade ni se reescribe nada."""
    st = (style or "").strip()
    return f"{st}: {text}" if st else text


_INTERACTIONS = {"bad": False}      # si la API de «interactions» falla una vez, no se vuelve a intentar en esta sesión


def _find_audio(o):
    """Busca en cualquier respuesta JSON un bloque de audio en base64 → (b64, mime)."""
    if isinstance(o, dict):
        d = o.get("data")
        if isinstance(d, str) and len(d) > 2000:
            return d, str(o.get("mime_type") or o.get("mimeType") or "")
        for v in o.values():
            r = _find_audio(v)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _find_audio(v)
            if r:
                return r
    return None


def _write_pcm(b64: str, mime: str, out_wav: str) -> None:
    import base64
    import wave
    pcm = base64.b64decode(b64)
    rate = 24000
    m = re.search(r"rate=(\d+)", mime or "")
    if m:
        rate = int(m.group(1))
    with wave.open(out_wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


def _gemini_interactions(text: str, voice: str, model: str, style: str, key: str, out_wav: str) -> bool:
    """Modelos 3.8: el texto va TAL CUAL y el estilo va aparte (speech_metadata), así nunca se lee en voz alta.
    Devuelve False si esta forma no funciona (el llamador usa generateContent)."""
    if _INTERACTIONS["bad"]:
        return False
    body = {"model": model,
            "input": [{"type": "user_input", "content": [{"type": "text", "text": text,
                                                           "annotations": [{"type": "speech_metadata", "style": style}]}]}],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": voice}]}}
    req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/interactions",
                                 data=json.dumps(body).encode(), method="POST",
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json", "Api-Revision": "2026-05-20"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read())
        found = _find_audio(data)
        if not found:
            raise ValueError("sin audio en la respuesta")
        _write_pcm(found[0], found[1], out_wav)
        return True
    except urllib.error.HTTPError as e:
        if e.code in (429, 500, 503):
            raise RuntimeError(f"Gemini respondió {e.code}; reintenta en un momento.")
        _INTERACTIONS["bad"] = True
        return False
    except Exception:
        _INTERACTIONS["bad"] = True
        return False


def gemini_synthesize(text: str, voice: str, model: str, style: str, out_wav: str) -> None:
    """Genera audio con Gemini TTS y lo guarda como WAV (PCM 24 kHz, 16 bit, mono)."""
    import base64
    import wave
    key = get_key()
    if not key:
        raise RuntimeError("Falta la API key de Gemini (🎙 Voces → Gemini).")
    model = model or DEFAULT_GEMINI_MODEL
    voice = voice or "Kore"
    if (style or "").strip() and "3.8" in model and _gemini_interactions(text, voice, model, (style or "").strip(), key, out_wav):
        return
    prompt = style_prompt(style, text)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def body(form: int) -> dict:
        vc = {"voice": voice} if form == 1 else {"prebuiltVoiceConfig": {"voiceName": voice}}
        return {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": vc}}}

    forms = [1, 2] if ("3." in model) else [2, 1]
    last = None
    for form in forms:
        for attempt in range(3):
            req = urllib.request.Request(url, data=json.dumps(body(form)).encode(), method="POST",
                                         headers={"x-goog-api-key": key, "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    data = json.loads(r.read())
                parts = data["candidates"][0]["content"]["parts"]
                inline = next(p["inlineData"] for p in parts if "inlineData" in p)
                pcm = base64.b64decode(inline["data"])
                rate = 24000
                m = re.search(r"rate=(\d+)", inline.get("mimeType", ""))
                if m:
                    rate = int(m.group(1))
                with wave.open(out_wav, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(rate)
                    w.writeframes(pcm)
                return
            except urllib.error.HTTPError as e:
                msg = e.read().decode("utf-8", "replace")[:300]
                last = f"Gemini respondió {e.code}: {msg}"
                if e.code in (429, 500, 503) and attempt < 2:
                    time.sleep(2 ** attempt * 3)
                    continue
                break  # 400 u otro: prueba el otro formato de voz
            except (KeyError, StopIteration, IndexError):
                last = "Gemini no devolvió audio (¿texto demasiado largo o bloqueado?)."
                break
    raise RuntimeError(last or "No se pudo generar la voz con Gemini.")
