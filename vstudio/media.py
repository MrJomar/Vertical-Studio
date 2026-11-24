"""Fondos (imágenes con Ken Burns, videos, degradado animado), lector de video y subtítulos."""
from __future__ import annotations

import math
import os
import random
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter

from .core import (IMAGE_EXT, VIDEO_EXT, clamp, dim, ffmpeg_bin, get_font, hash_key, lerp, mix_color,
                   paste_layer, popen_kwargs, probe_video, run_quiet, seg, text_layer, ease, wrap_lines)


# --------------------------------------------------------------------------- video
def _vf_cover(w: int, h: int, fps: int, fit: str) -> str:
    if fit == "blur":
        return (f"fps={fps},split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                f"scale={w // 8}:{h // 8},boxblur=6:2,scale={w}:{h},eq=brightness=-0.12[bg];"
                f"[b]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")
    return f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"


class VideoReader:
    """Lee fotogramas RGB secuenciales de un video vía FFmpeg (con bucle opcional)."""

    def __init__(self, path: str, w: int, h: int, fps: int, start: float = 0.0, duration: float | None = None,
                 fit: str = "cover", loop: bool = True, vf: str | None = None):
        self.w, self.h = w, h
        cmd = [ffmpeg_bin(), "-v", "error"]
        if loop:
            cmd += ["-stream_loop", "-1"]
        if start > 0:
            cmd += ["-ss", f"{start:.3f}"]
        cmd += ["-i", path]
        if duration is not None:
            cmd += ["-t", f"{duration:.3f}"]
        cmd += ["-an", "-vf", vf or _vf_cover(w, h, fps, fit), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **popen_kwargs())
        self.size = w * h * 3
        self.last: Image.Image | None = None
        self.index = -1

    def read_np(self) -> np.ndarray | None:
        buf = self.proc.stdout.read(self.size)
        if not buf or len(buf) < self.size:
            return None
        return np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3)

    def frame_at(self, index: int) -> Image.Image:
        """Avanza hasta el fotograma `index` (solo hacia adelante)."""
        while self.index < index:
            arr = self.read_np()
            if arr is None:
                break
            self.last = Image.fromarray(arr.copy(), "RGB")
            self.index += 1
        return self.last or Image.new("RGB", (self.w, self.h), (0, 0, 0))

    def close(self) -> None:
        try:
            self.proc.kill()
            self.proc.stdout.close()
        except Exception:
            pass


def grab_frame(path: str, t: float, w: int, h: int, fit: str = "cover") -> Image.Image:
    cmd = [ffmpeg_bin(), "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", path, "-frames:v", "1",
           "-vf", _vf_cover(w, h, 30, fit).replace("fps=30,", ""), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    r = run_quiet(cmd)
    if len(r.stdout) >= w * h * 3:
        return Image.fromarray(np.frombuffer(r.stdout[: w * h * 3], np.uint8).reshape(h, w, 3).copy(), "RGB")
    return Image.new("RGB", (w, h), (0, 0, 0))


# --------------------------------------------------------------------------- imágenes
_img_cache: dict = {}


def load_image(path: str, max_side: int = 3000) -> Image.Image:
    key = (path, os.path.getmtime(path))
    if key in _img_cache:
        return _img_cache[key]
    im = Image.open(path)
    try:
        im.seek(0)
    except Exception:
        pass
    im = im.convert("RGB")
    s = max(im.size)
    if s > max_side:
        k = max_side / s
        im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    if len(_img_cache) > 24:
        _img_cache.clear()
    _img_cache[key] = im
    return im


def blur_fit(img: Image.Image, w: int, h: int) -> Image.Image:
    k = max(w / img.width, h / img.height)
    small = img.resize((max(1, int(img.width * k / 8)), max(1, int(img.height * k / 8))), Image.BILINEAR)
    left, top = (small.width - w // 8) // 2, (small.height - h // 8) // 2
    small = small.crop((left, top, left + w // 8, top + h // 8)).filter(ImageFilter.GaussianBlur(3))
    bg = small.resize((w, h), Image.BICUBIC)
    bg = Image.blend(bg, Image.new("RGB", (w, h), (0, 0, 0)), 0.35)
    k2 = min(w / img.width, h / img.height)
    fg = img.resize((max(1, int(img.width * k2)), max(1, int(img.height * k2))), Image.LANCZOS)
    bg.paste(fg, ((w - fg.width) // 2, (h - fg.height) // 2))
    return bg


# --------------------------------------------------------------------------- fondos
class GradientBG:
    """Degradado con manchas de luz animadas (estilo vector)."""

    def __init__(self, theme: dict, w: int, h: int, seed: int = 0):
        self.w, self.h = w, h
        self.sw, self.sh = max(36, w // 10), max(64, h // 10)
        self.t = theme
        r = random.Random(seed)
        self.blobs = [(r.random(), r.random(), r.uniform(0.5, 1.2), r.uniform(0.2, 0.5), r.random() * 6.28,
                       r.uniform(0.15, 0.4)) for _ in range(5)]
        y = np.linspace(0, 1, self.sh, dtype=np.float32)[:, None, None]
        c1, c2 = np.array(theme["bg1"], np.float32), np.array(theme["bg2"], np.float32)
        self.base = c1 * (1 - y) + c2 * y  # (sh,1,3)
        self.yy, self.xx = np.mgrid[0:self.sh, 0:self.sw].astype(np.float32)
        self.yy /= self.sh
        self.xx /= self.sw

    def frame(self, t: float) -> Image.Image:
        arr = np.repeat(self.base, self.sw, axis=1).copy()
        acc = np.array(self.t["accent"], np.float32)
        acc2 = np.array(self.t["accent2"], np.float32)
        for i, (bx, by, sp, rad, ph, st) in enumerate(self.blobs):
            cx = 0.5 + 0.45 * math.sin(t * 0.25 * sp + ph + bx * 6)
            cy = 0.5 + 0.45 * math.cos(t * 0.21 * sp + ph * 1.3 + by * 6)
            d2 = ((self.xx - cx) * (self.sw / self.sh)) ** 2 + (self.yy - cy) ** 2
            m = np.exp(-d2 / (rad * rad * 0.35))[..., None] * st * 0.55
            arr += m * (acc if i % 2 == 0 else acc2) * 0.55
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
        return img.resize((self.w, self.h), Image.BICUBIC)


class _ImageItem:
    def __init__(self, path: str, w: int, h: int, fit: str, seed: int, kenburns: bool = True):
        self.w, self.h, self.fit, self.kb = w, h, fit, kenburns
        self.src = load_image(path)
        r = random.Random(seed)
        self.z0, self.z1 = (1.0, 1.0 + r.uniform(0.10, 0.18)) if r.random() < 0.6 else (1.16, 1.0)
        self.px, self.py = r.uniform(-1, 1), r.uniform(-1, 1)
        self.static = blur_fit(self.src, w, h) if fit == "blur" else None
        if self.static is not None:
            self.src = self.static  # Ken Burns sobre la composición ya difuminada

    def frame(self, u: float, span: float) -> Image.Image:
        S = self.src
        p = ease("in_out", u / max(span, 1e-6)) if self.kb else 0.0
        z = lerp(self.z0, self.z1, p)
        s0 = max(self.w / S.width, self.h / S.height)
        vw, vh = self.w / (s0 * z), self.h / (s0 * z)
        mx, my = (S.width - vw) / 2, (S.height - vh) / 2
        k = (p - 0.5) * 0.9 if self.kb else 0.0
        cx = S.width / 2 + mx * self.px * k * 2
        cy = S.height / 2 + my * self.py * k * 2
        box = (cx - vw / 2, cy - vh / 2, cx + vw / 2, cy + vh / 2)
        return S.resize((self.w, self.h), Image.BICUBIC, box=box)


class _VideoItem:
    def __init__(self, path: str, w: int, h: int, fps: int, fit: str, preview: bool, start: float = 0.0):
        self.path, self.w, self.h, self.fps, self.fit, self.preview, self.start = path, w, h, fps, fit, preview, start
        self.reader: VideoReader | None = None

    def frame(self, u: float, span: float) -> Image.Image:
        if self.preview:
            return grab_frame(self.path, self.start + u, self.w, self.h, self.fit)
        if self.reader is None:
            self.reader = VideoReader(self.path, self.w, self.h, self.fps, self.start, fit=self.fit)
        return self.reader.frame_at(int(round(u * self.fps)))

    def close(self):
        if self.reader:
            self.reader.close()
            self.reader = None


class Background:
    """Secuencia de imágenes/videos a lo largo de `duration` con fundido cruzado; o degradado animado."""

    XFADE = 0.4

    def __init__(self, ctx, media: list, duration: float, fit: str = "cover", dim_amount: float = 0.35,
                 seed: int = 0, kenburns: bool = True):
        self.ctx, self.duration, self.dim = ctx, duration, dim_amount
        self.items: list = []
        self.begins: list[float] = []
        self.ends: list[float] = []
        self.gradient = GradientBG(ctx.theme, ctx.w, ctx.h, seed)
        paths, durs = [], []
        for m in media or []:
            p = m.get("path") if isinstance(m, dict) else m
            p = ctx.resolve(p)
            if p and os.path.isfile(p) and Path(p).suffix.lower() in (IMAGE_EXT | VIDEO_EXT):
                paths.append(p)
                durs.append(float(m.get("duration", 0)) if isinstance(m, dict) else 0.0)
        if not paths:
            return
        fixed = sum(d for d in durs if d > 0)
        free = [i for i, d in enumerate(durs) if d <= 0]
        rest = max(0.5 * len(free), duration - fixed)
        for i in free:
            durs[i] = rest / len(free) if free else 0
        scale = duration / max(sum(durs), 1e-6)
        durs = [d * scale for d in durs]
        t = 0.0
        for i, (p, d) in enumerate(zip(paths, durs)):
            begin = max(0.0, t - (self.XFADE if i > 0 else 0.0))
            if Path(p).suffix.lower() in VIDEO_EXT:
                it = _VideoItem(p, ctx.w, ctx.h, ctx.fps, fit, ctx.preview)
            else:
                it = _ImageItem(p, ctx.w, ctx.h, fit, seed + i * 7919 + len(p), kenburns)
            self.items.append(it)
            self.begins.append(begin)
            self.ends.append(t + d)
            t += d

    def frame(self, t: float) -> Image.Image:
        if not self.items:
            return self.gradient.frame(t)
        active = [i for i in range(len(self.items)) if self.begins[i] <= t < self.ends[i]]
        if not active:
            active = [len(self.items) - 1] if t >= self.ends[-1] else [0]
        i0 = active[0]
        img = self.items[i0].frame(t - self.begins[i0], self.ends[i0] - self.begins[i0])
        if len(active) > 1:
            i1 = active[1]
            nxt = self.items[i1].frame(t - self.begins[i1], self.ends[i1] - self.begins[i1])
            a = ease("in_out", (t - self.begins[i1]) / self.XFADE)
            img = Image.blend(img, nxt, clamp(a))
        return dim(img, self.dim)

    def close(self):
        for it in self.items:
            if hasattr(it, "close"):
                it.close()


# --------------------------------------------------------------------------- subtítulos
class CaptionTrack:
    """Subtítulos estilo Shorts: grupos de pocas palabras con la palabra activa resaltada."""

    def __init__(self, words: list, ctx, max_words: int = 4, max_chars: int = 22):
        s = ctx.settings
        self.ctx = ctx
        self.size = int(s.get("caption_size", 78))
        self.upper = bool(s.get("caption_upper", True))
        self.y = float(s.get("caption_y", 0.74)) * ctx.h
        self.fill = ctx.theme["text"]
        self.hl = ctx.theme["hl"]
        self.font = s.get("caption_font", "display")
        self.groups: list[list[tuple[str, float, float]]] = []
        cur: list = []
        chars = 0
        for w in words:
            txt = str(w[0]).strip()
            if not txt:
                continue
            if cur and (len(cur) >= max_words or chars + len(txt) > max_chars):
                self.groups.append(cur)
                cur, chars = [], 0
            cur.append((txt.upper() if self.upper else txt, float(w[1]), float(w[2])))
            chars += len(txt) + 1
            if txt[-1] in ".!?…" and len(cur) >= 2:
                self.groups.append(cur)
                cur, chars = [], 0
        if cur:
            self.groups.append(cur)
        self.style = ctx.settings.get("caption_style", "clasico")
        self._cache: dict = {}

    def _layer(self, gi: int, active: int) -> Image.Image:
        key = (gi, active, self.style)
        if key in self._cache:
            return self._cache[key]
        g = self.groups[gi]
        font = get_font(self.font, self.size)
        space = font.getlength(" ") if hasattr(font, "getlength") else self.size * 0.3
        maxw = int(self.ctx.w * 0.88)
        # reparte en 1-2 líneas
        widths = [font.getlength(w[0]) for w in g]
        lines, cur, cw = [], [], 0.0
        for i, w in enumerate(widths):
            if cur and cw + space + w > maxw:
                lines.append(cur)
                cur, cw = [], 0.0
            cur.append(i)
            cw += w + (space if len(cur) > 1 else 0)
        lines.append(cur)
        asc, desc = font.getmetrics()
        lh = int((asc + desc) * 1.05)
        stroke = max(4, self.size // 9) if self.style not in ("caja", "suave") else 0
        pad = stroke + 6
        W = int(maxw + pad * 2)
        H = lh * len(lines) + pad * 2
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        y = pad
        for line in lines:
            tw = sum(widths[i] for i in line) + space * (len(line) - 1)
            x = (W - tw) / 2
            for i in line:
                col = self.hl if i == active else self.fill
                if self.style in ("caja", "suave"):
                    a_ = 255 if i == active else (210 if self.style == "suave" else 190)
                    if i == active:
                        d.rounded_rectangle([x - 8, y + lh * 0.1, x + widths[i] + 8, y + lh * 0.98], radius=10,
                                            outline=(120, 170, 255, 255), width=3, fill=(40, 70, 160, 70))
                    d.text((x + 2, y + 3), g[i][0], font=font, fill=(0, 0, 0, 175))
                    d.text((x, y), g[i][0], font=font, fill=((255, 255, 255) if i == active else (235, 235, 245)) + (a_,))
                    x += widths[i] + space
                    continue
                if False:
                    col = (255, 255, 255) if i == active else (232, 232, 240)
                    if i == active:
                        d.rounded_rectangle([x - 8, y + lh * 0.1, x + widths[i] + 8, y + lh * 0.98], radius=10,
                                            outline=(120, 170, 255, 255), width=4, fill=(40, 70, 160, 90))
                d.text((x + 3, y + 5), g[i][0], font=font, fill=(0, 0, 0, 140), stroke_width=stroke,
                       stroke_fill=(0, 0, 0, 140))
                d.text((x, y), g[i][0], font=font, fill=tuple(col) + (255,), stroke_width=stroke,
                       stroke_fill=(0, 0, 0, 255))
                x += widths[i] + space
            y += lh
        if len(self._cache) > 300:
            self._cache.clear()
        self._cache[key] = img
        return img

    def draw(self, canvas: Image.Image, t: float) -> None:
        for gi, g in enumerate(self.groups):
            nxt_start = self.groups[gi + 1][0][1] if gi + 1 < len(self.groups) else 1e9
            t0, t1 = g[0][1] - 0.04, min(g[-1][2] + 0.25, nxt_start - 0.02)
            if t0 <= t < t1:
                active = 0
                for i, w in enumerate(g):
                    if w[1] <= t:
                        active = i
                pop = seg(t, g[0][1] - 0.04, g[0][1] + 0.14, "out_back")
                paste_layer(canvas, self._layer(gi, active), self.ctx.w / 2, self.y,
                            scale=0.82 + 0.18 * pop, alpha=clamp(pop * 1.4))
                return
