"""Utilidades base: rutas, easing, fuentes, texto, codificador FFmpeg, mezcla de audio."""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
CACHE_DIR = Path(os.environ.get("VSTUDIO_CACHE", str(APP_DIR / "cache")))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".flv", ".ts"}


# --------------------------------------------------------------------------- procesos
def _local_bin(name: str) -> str | None:
    exe = name + (".exe" if os.name == "nt" else "")
    p = APP_DIR / "bin" / exe
    return str(p) if p.exists() else None


def ffmpeg_bin() -> str:
    return os.environ.get("FFMPEG") or _local_bin("ffmpeg") or shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_bin() -> str:
    return os.environ.get("FFPROBE") or _local_bin("ffprobe") or shutil.which("ffprobe") or "ffprobe"


def popen_kwargs() -> dict:
    if os.name == "nt":  # sin ventanas de consola emergentes
        return {"creationflags": 0x08000000}
    return {}


def run_quiet(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, **popen_kwargs(), **kw)


def probe_duration(path: str | os.PathLike) -> float:
    r = run_quiet([ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
                   "-of", "default=nw=1:nk=1", str(path)])
    try:
        return float(r.stdout.decode().strip())
    except ValueError:
        return 0.0


def probe_video(path: str | os.PathLike) -> dict:
    r = run_quiet([ffprobe_bin(), "-v", "error", "-select_streams", "v:0", "-show_entries",
                   "stream=width,height,r_frame_rate,duration", "-of", "json", str(path)])
    try:
        s = json.loads(r.stdout.decode())["streams"][0]
        num, den = (s.get("r_frame_rate", "30/1").split("/") + ["1"])[:2]
        return {"w": int(s["width"]), "h": int(s["height"]),
                "fps": float(num) / float(den or 1), "duration": float(s.get("duration") or 0)}
    except Exception:
        return {"w": 1920, "h": 1080, "fps": 30.0, "duration": 0.0}


def has_audio(path: str | os.PathLike) -> bool:
    r = run_quiet([ffprobe_bin(), "-v", "error", "-select_streams", "a:0", "-show_entries",
                   "stream=codec_type", "-of", "default=nw=1:nk=1", str(path)])
    return b"audio" in r.stdout


# --------------------------------------------------------------------------- easing
def clamp(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return a if x < a else b if x > b else x


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _in_out(t): return t * t * (3 - 2 * t)
def _in_out_cubic(t): return 4 * t ** 3 if t < 0.5 else 1 - ((-2 * t + 2) ** 3) / 2
def _out_cubic(t): return 1 - (1 - t) ** 3
def _out_expo(t): return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)
def _out_back(t): return 1 + 2.70158 * (t - 1) ** 3 + 1.70158 * (t - 1) ** 2
def _out_elastic(t):
    if t <= 0: return 0.0
    if t >= 1: return 1.0
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi) / 3) + 1


EASE = {"linear": lambda t: t, "in_out": _in_out, "in_out_cubic": _in_out_cubic,
        "out_cubic": _out_cubic, "out_expo": _out_expo, "out_back": _out_back,
        "out_elastic": _out_elastic}


def ease(name: str, t: float) -> float:
    return EASE[name](clamp(t))


def seg(t: float, t0: float, t1: float, name: str = "out_cubic") -> float:
    """Progreso eased de 0..1 de t entre t0 y t1."""
    if t1 <= t0:
        return 1.0 if t >= t1 else 0.0
    return ease(name, (t - t0) / (t1 - t0))


# --------------------------------------------------------------------------- colores
def parse_color(c, default=(255, 255, 255)) -> tuple[int, int, int]:
    if c is None:
        return default
    if isinstance(c, (list, tuple)) and len(c) >= 3:
        return int(c[0]), int(c[1]), int(c[2])
    if isinstance(c, str):
        s = c.strip().lstrip("#")
        if len(s) == 3:
            s = "".join(ch * 2 for ch in s)
        if len(s) == 6:
            try:
                return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
            except ValueError:
                pass
    return default


def mix_color(a, b, t: float):
    return tuple(int(round(lerp(a[i], b[i], t))) for i in range(3))


THEMES = {
    "neon": dict(bg1=(8, 10, 28), bg2=(52, 10, 82), accent=(0, 229, 255), accent2=(255, 64, 129),
                 text=(255, 255, 255), sub=(205, 210, 230), hl=(255, 226, 52),
                 ocean=(8, 14, 34), land=(30, 42, 78), border=(70, 96, 160), grid=(20, 30, 62),
                 pick=(0, 229, 255)),
    "oscuro": dict(bg1=(14, 14, 16), bg2=(40, 40, 46), accent=(255, 196, 0), accent2=(255, 90, 54),
                   text=(255, 255, 255), sub=(210, 210, 214), hl=(255, 196, 0),
                   ocean=(16, 18, 22), land=(46, 50, 58), border=(86, 92, 104), grid=(26, 29, 35),
                   pick=(255, 196, 0)),
    "retro": dict(bg1=(34, 18, 40), bg2=(120, 44, 60), accent=(255, 150, 60), accent2=(255, 215, 120),
                  text=(255, 244, 224), sub=(240, 214, 190), hl=(255, 215, 120),
                  ocean=(38, 26, 52), land=(92, 62, 78), border=(160, 112, 112), grid=(52, 36, 66),
                  pick=(255, 150, 60)),
    "papel": dict(bg1=(246, 238, 218), bg2=(226, 210, 176), accent=(196, 54, 38), accent2=(32, 78, 120),
                  text=(32, 28, 24), sub=(84, 74, 62), hl=(196, 54, 38),
                  ocean=(214, 226, 226), land=(240, 230, 204), border=(150, 132, 100), grid=(200, 214, 214),
                  pick=(196, 54, 38)),
    "esmeralda": dict(bg1=(6, 26, 24), bg2=(10, 74, 62), accent=(88, 255, 170), accent2=(255, 214, 90),
                      text=(240, 255, 250), sub=(190, 226, 214), hl=(255, 214, 90),
                      ocean=(6, 22, 24), land=(22, 62, 58), border=(60, 130, 112), grid=(12, 40, 40),
                      pick=(88, 255, 170)),
}


def get_theme(settings: dict) -> dict:
    t = dict(THEMES.get(settings.get("theme", "oscuro"), THEMES["oscuro"]))
    for k, v in (settings.get("theme_colors") or {}).items():
        if k in t:
            t[k] = parse_color(v, t[k])
    return t


# --------------------------------------------------------------------------- fuentes
_FONT_DIRS = [
    APP_DIR / "fonts",
    Path("C:/Windows/Fonts"),
    Path(os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts")),
    Path("/Library/Fonts"), Path("/System/Library/Fonts"), Path(os.path.expanduser("~/Library/Fonts")),
    Path("/usr/share/fonts"), Path(os.path.expanduser("~/.fonts")),
]
_ROLE_FONTS = {
    "display": ["Anton-Regular.ttf", "Bebas-Regular.ttf", "BebasNeue-Regular.ttf", "impact.ttf",
                "ariblk.ttf", "arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"],
    "bold": ["Montserrat-ExtraBold.ttf", "Montserrat-Bold.ttf", "segoeuib.ttf", "arialbd.ttf",
             "Arial Bold.ttf", "DejaVuSans-Bold.ttf"],
    "regular": ["Montserrat-Medium.ttf", "segoeui.ttf", "arial.ttf", "Arial.ttf", "DejaVuSans.ttf"],
}
_font_index: dict[str, str] | None = None


def _index_fonts() -> dict[str, str]:
    global _font_index
    if _font_index is None:
        _font_index = {}
        for d in _FONT_DIRS:
            if not d.exists():
                continue
            try:
                for root, _dirs, files in os.walk(d):
                    for f in files:
                        if f.lower().endswith((".ttf", ".otf", ".ttc")):
                            _font_index.setdefault(f.lower(), os.path.join(root, f))
            except OSError:
                pass
    return _font_index


def find_font(spec: str) -> str | None:
    if not spec:
        return None
    if os.path.isfile(spec):
        return spec
    idx = _index_fonts()
    if spec.lower() in idx:
        return idx[spec.lower()]
    for name in _ROLE_FONTS.get(spec, []):
        if name.lower() in idx:
            return idx[name.lower()]
    return None


@lru_cache(maxsize=256)
def get_font(spec: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = find_font(spec) or find_font("bold")
    if path:
        try:
            return ImageFont.truetype(path, int(size))
        except OSError:
            pass
    return ImageFont.load_default()


# --------------------------------------------------------------------------- texto
_probe = ImageDraw.Draw(Image.new("L", (4, 4)))


def wrap_lines(text: str, font, max_w: float) -> list[str]:
    out: list[str] = []
    for para in str(text).split("\n"):
        cur = ""
        for w in para.split():
            t = (cur + " " + w).strip()
            if cur and _probe.textlength(t, font=font) > max_w:
                out.append(cur)
                cur = w
            else:
                cur = t
        out.append(cur)
    return out


_layer_cache: dict = {}


def text_layer(text: str, font_spec: str = "bold", size: int = 60, fill=(255, 255, 255),
               stroke: int = 0, stroke_fill=(0, 0, 0), max_w: int = 900, align: str = "center",
               spacing: float = 0.1, shadow: int = 0, upper: bool = False) -> Image.Image:
    """Capa RGBA con texto ajustado (cacheada)."""
    text = str(text).upper() if upper else str(text)
    key = (text, font_spec, size, tuple(fill), stroke, tuple(stroke_fill), max_w, align, spacing, shadow)
    hit = _layer_cache.get(key)
    if hit is not None:
        return hit
    font = get_font(font_spec, size)
    lines = wrap_lines(text, font, max_w)
    asc, desc = font.getmetrics() if hasattr(font, "getmetrics") else (size, size // 4)
    lh = int((asc + desc) * (1 + spacing))
    widths = [_probe.textlength(l, font=font) for l in lines]
    pad = stroke + shadow + 4
    W = int(max(widths + [1]) + pad * 2)
    H = int(lh * len(lines) + pad * 2)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = pad
    for line, lw in zip(lines, widths):
        x = pad if align == "left" else (W - lw) / 2 if align == "center" else W - pad - lw
        if shadow:
            d.text((x + shadow, y + shadow), line, font=font, fill=(0, 0, 0, 150),
                   stroke_width=stroke, stroke_fill=(0, 0, 0, 150))
        d.text((x, y), line, font=font, fill=tuple(fill) + (255,), stroke_width=stroke,
               stroke_fill=tuple(stroke_fill) + (255,))
        y += lh
    if len(_layer_cache) > 600:
        _layer_cache.clear()
    _layer_cache[key] = img
    return img


def fit_text_layer(text: str, font_spec: str, max_size: int, min_size: int, max_w: int, max_h: int,
                   **kw) -> Image.Image:
    size = max_size
    while True:
        layer = text_layer(text, font_spec, size, max_w=max_w, **kw)
        if layer.height <= max_h or size <= min_size:
            return layer
        size = max(min_size, int(size * 0.92))


def paste_layer(canvas: Image.Image, layer: Image.Image, x: float, y: float, scale: float = 1.0,
                alpha: float = 1.0, anchor: str = "center") -> None:
    """Pega la capa; (x,y) es el centro, o el borde superior ("top"), inferior ("bottom") o izquierdo."""
    if alpha <= 0.004 or scale <= 0.01 or layer is None:
        return
    if abs(scale - 1.0) > 1e-3:
        layer = layer.resize((max(1, int(layer.width * scale)), max(1, int(layer.height * scale))),
                             Image.BILINEAR)
    if alpha < 0.996:
        a = layer.getchannel("A").point([int(i * alpha) for i in range(256)])
        layer = layer.copy()
        layer.putalpha(a)
    if anchor == "center":
        px, py = x - layer.width / 2, y - layer.height / 2
    elif anchor == "top":
        px, py = x - layer.width / 2, y
    elif anchor == "bottom":
        px, py = x - layer.width / 2, y - layer.height
    elif anchor == "left":
        px, py = x, y - layer.height / 2
    else:
        px, py = x, y
    canvas.paste(layer, (int(px), int(py)), layer)


def gradient_image(w: int, h: int, c1, c2, vertical: bool = True) -> Image.Image:
    n = h if vertical else w
    t = np.linspace(0, 1, n, dtype=np.float32)[:, None]
    c1 = np.array(c1, np.float32)
    c2 = np.array(c2, np.float32)
    col = (c1 * (1 - t) + c2 * t).astype(np.uint8)  # (n,3)
    arr = np.repeat(col[:, None, :], w, axis=1) if vertical else np.repeat(col[None, :, :], h, axis=0)
    return Image.fromarray(arr, "RGB")


def shade_overlay(w: int, h: int, top: float = 0.55, bottom: float = 0.75) -> Image.Image:
    """RGBA negro que oscurece arriba y abajo (para legibilidad)."""
    y = np.linspace(0, 1, h, dtype=np.float32)
    a = np.maximum(top * (1 - y / 0.35).clip(0, 1) ** 1.5, bottom * ((y - 0.55) / 0.45).clip(0, 1) ** 1.3)
    arr = np.zeros((h, w, 4), np.uint8)
    arr[..., 3] = np.repeat((a * 255).astype(np.uint8)[:, None], w, axis=1)
    return Image.fromarray(arr, "RGBA")


def dim(img: Image.Image, amount: float) -> Image.Image:
    if amount <= 0:
        return img
    return Image.blend(img, Image.new("RGB", img.size, (0, 0, 0)), clamp(amount))


def hash_key(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- codificador
_nvenc_ok: bool | None = None


def nvenc_available() -> bool:
    global _nvenc_ok
    if _nvenc_ok is None:
        try:
            r = run_quiet([ffmpeg_bin(), "-v", "error", "-f", "lavfi", "-i", "color=black:s=256x256:d=0.2",
                           "-c:v", "h264_nvenc", "-f", "null", "-"], timeout=20)
            _nvenc_ok = r.returncode == 0
        except Exception:
            _nvenc_ok = False
    return _nvenc_ok


_amf_ok: bool | None = None


def amf_available() -> bool:
    """GPU AMD (Radeon) con codificador AMF."""
    global _amf_ok
    if _amf_ok is None:
        try:
            r = run_quiet([ffmpeg_bin(), "-v", "error", "-f", "lavfi", "-i", "color=black:s=256x256:d=0.2",
                           "-c:v", "h264_amf", "-f", "null", "-"], timeout=20)
            _amf_ok = r.returncode == 0
        except Exception:
            _amf_ok = False
    return _amf_ok


def gpu_name() -> str:
    return "NVIDIA (NVENC)" if nvenc_available() else "AMD (AMF)" if amf_available() else ""


def video_codec_args(encoder: str, quality: str = "alta") -> tuple[list[str], str]:
    enc = encoder
    if enc == "auto":
        enc = "nvenc" if nvenc_available() else "amf" if amf_available() else "x264"
    if enc == "nvenc" and not nvenc_available():
        enc = "amf" if amf_available() else "x264"
    if enc == "amf" and not amf_available():
        enc = "x264"
    cq = {"borrador": 28, "normal": 23, "alta": 19, "maxima": 16}.get(quality, 19)
    if enc == "nvenc":
        return (["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", str(cq),
                 "-b:v", "0", "-profile:v", "high"], "nvenc")
    if enc == "amf":
        return (["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", str(cq), "-qp_p", str(cq + 2),
                 "-qp_b", str(cq + 4), "-profile:v", "high"], "amf")
    preset = "ultrafast" if quality == "borrador" else "veryfast"
    return (["-c:v", "libx264", "-preset", preset, "-crf", str(cq - 1), "-profile:v", "high"], "x264")


class Encoder:
    def __init__(self, path: str, w: int, h: int, fps: int, encoder: str = "auto", quality: str = "alta"):
        args, self.used = video_codec_args(encoder, quality)
        cmd = [ffmpeg_bin(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", *args, "-pix_fmt", "yuv420p",
               "-movflags", "+faststart", str(path)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, **popen_kwargs())
        self.w, self.h = w, h

    def write(self, img: Image.Image) -> None:
        if img.size != (self.w, self.h):
            img = img.resize((self.w, self.h), Image.BILINEAR)
        if img.mode != "RGB":
            img = img.convert("RGB")
        try:
            self.proc.stdin.write(img.tobytes())
        except (BrokenPipeError, OSError):
            raise RuntimeError("FFmpeg se cerró: " + self.proc.stderr.read().decode(errors="replace")[-600:])

    def close(self) -> None:
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        err = self.proc.stderr.read().decode(errors="replace")
        self.proc.wait()
        if self.proc.returncode not in (0, None):
            raise RuntimeError("FFmpeg falló al codificar: " + err[-800:])

    def abort(self) -> None:
        try:
            self.proc.kill()
        except Exception:
            pass


# --------------------------------------------------------------------------- audio final
def mix_audio(tracks: list[tuple[str, float, float]], total: float, music: str | None,
              music_vol: float, out_path: str, duck: bool = True) -> str | None:
    """tracks: (archivo, inicio_s, volumen). Devuelve ruta del audio mezclado (m4a/wav) o None."""
    if not tracks and not music:
        return None
    cmd = [ffmpeg_bin(), "-y", "-v", "error"]
    chains: list[str] = []
    labels: list[str] = []
    idx = 0
    for path, start, vol in tracks:
        cmd += ["-i", path]
        ms = max(0, int(start * 1000))
        chains.append(f"[{idx}:a]aresample=44100,aformat=channel_layouts=stereo,"
                      f"adelay={ms}|{ms},volume={vol:.3f}[v{idx}]")
        labels.append(f"[v{idx}]")
        idx += 1
    voice = None
    if labels:
        chains.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=longest[voice]")
        voice = "[voice]"
    final = voice
    if music and os.path.isfile(music):
        cmd += ["-stream_loop", "-1", "-i", music]
        fade = max(0.0, total - 1.5)
        chains.append(f"[{idx}:a]aresample=44100,aformat=channel_layouts=stereo,volume={music_vol:.3f},"
                      f"atrim=0:{total:.3f},afade=t=out:st={fade:.3f}:d=1.5[mus]")
        if voice and duck:
            chains.append("[voice]asplit[vo1][vo2]")
            chains.append("[mus][vo2]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=450[musd]")
            chains.append("[vo1][musd]amix=inputs=2:normalize=0:duration=longest[mix]")
            final = "[mix]"
        elif voice:
            chains.append("[voice][mus]amix=inputs=2:normalize=0:duration=longest[mix]")
            final = "[mix]"
        else:
            final = "[mus]"
    if final is None:
        return None
    chains.append(f"{final}apad[fin]")      # rellena con silencio hasta la duración del video
    final = "[fin]"
    cmd += ["-filter_complex", ";".join(chains), "-map", final, "-t", f"{total:.3f}",
            "-c:a", "aac", "-b:a", "192k", out_path]
    r = run_quiet(cmd)
    if r.returncode != 0:
        raise RuntimeError("Falló la mezcla de audio: " + r.stderr.decode(errors="replace")[-600:])
    return out_path


def mux(video: str, audio: str | None, out_path: str, total: float) -> None:
    if audio:
        cmd = [ffmpeg_bin(), "-y", "-v", "error", "-i", video, "-i", audio, "-map", "0:v:0", "-map", "1:a:0",
               "-c:v", "copy", "-c:a", "copy", "-t", f"{total:.3f}", "-movflags", "+faststart", out_path]
    else:
        cmd = [ffmpeg_bin(), "-y", "-v", "error", "-i", video, "-f", "lavfi", "-i",
               "anullsrc=r=44100:cl=stereo", "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
               "-c:a", "aac", "-b:a", "96k", "-t", f"{total:.3f}", "-movflags", "+faststart", out_path]
    r = run_quiet(cmd)
    if r.returncode != 0:
        raise RuntimeError("Falló el muxeo final: " + r.stderr.decode(errors="replace")[-600:])
