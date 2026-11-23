"""Animación vectorial por capas: fondos, personajes y objetos con animaciones sincronizadas a la voz."""
from __future__ import annotations

import json
import math
import random
import re
import unicodedata

import cv2
import numpy as np
from PIL import Image

from .core import clamp, ease, gradient_image, lerp, parse_color, seg
from .scenes import Scene
from PIL import ImageFilter
from .vector_assets import ASSETS, sprite as _raw_sprite

_sh_cache: dict = {}


_BEVEL = {"persona": 0.9, "puerta": 0.7, "pez": 0.8, "gato": 0.8, "cartel": 0.6, "etiqueta": 0.5, "pastilla": 0.6,
          "nariz": 0.8, "corazon": 0.9, "estrella": 0.7, "marca": 0.6, "pin": 0.8, "calendario": 0.5, "olor": 0.4,
          "regadera": 0.7, "flecha": 0.6, "hielo": 0.5, "esfera": 0.0}


def _bevel(im, k):
    a = np.asarray(im.getchannel("A"), np.float32) / 255.0
    sig = max(1.5, im.width * 0.025)
    b = cv2.GaussianBlur(a, (0, 0), sig)
    gx = cv2.Sobel(b, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(b, cv2.CV_32F, 0, 1, ksize=3)
    sh = np.clip(-(gx + gy) * (sig * 1.2), -1, 1)        # luz desde arriba-izquierda
    arr = np.asarray(im, np.float32).copy()
    rgb = arr[..., :3]
    up = np.clip(sh, 0, 1)[..., None]
    dn = np.clip(-sh, 0, 1)[..., None]
    rgb = rgb * (1 - dn * 0.45 * k) + (255 - rgb) * (up * 0.30 * k)
    # degradado vertical suave (arriba más claro)
    ys = np.linspace(1.08, 0.88, im.height, dtype=np.float32)[:, None, None]
    rgb = rgb * (1 + (ys - 1) * k)
    arr[..., :3] = np.clip(rgb, 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def sprite(name, width, params, shadow=True):
    base = _raw_sprite(name, width, params)
    kb = _BEVEL.get(name, 0.0)
    if kb:
        bk = ("bv", name, int(width), tuple(sorted((k, str(v)) for k, v in params.items())))
        hit = _sh_cache.get(bk)
        if hit is None:
            hit = _sh_cache[bk] = _bevel(base, kb)
        base = hit
    if not shadow:
        return base
    key = (name, int(width), tuple(sorted((k, str(v)) for k, v in params.items())))
    hit = _sh_cache.get(key)
    if hit is None:
        pad = max(6, int(base.width * 0.07))
        W, H = base.width + pad * 2, base.height + pad * 2
        a = Image.new("L", (W, H), 0)
        a.paste(base.getchannel("A"), (pad, pad + int(pad * 0.5)))
        a = a.filter(ImageFilter.GaussianBlur(max(2, pad * 0.45))).point([int(i * 0.42) for i in range(256)])
        out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        out.putalpha(a)
        out.alpha_composite(base, (pad, pad))
        if len(_sh_cache) > 400:
            _sh_cache.clear()
        hit = _sh_cache[key] = out
    return hit

BG_CHOICES = ["olas", "ladrillos", "azulejos", "niebla", "rayos", "cuarto", "cuadricula", "espacio", "degradado", "color"]
CAMERAS = ["", "push", "pull", "pan_left", "pan_right"]

DEFAULT_COLORS = {
    "ladrillos": ["#b0587a", "#4a1f3a", "#e8a0c0"],
    "olas": ["#c2506f", "#3a0f28", "#ffb0c8"],
    "azulejos": ["#2c8f8c", "#1b5f63", "#d8d0b8"],
    "niebla": ["#7ad84a", "#0f4a1a", "#b8ff7a"],
    "rayos": ["#2b8fa8", "#0a2a3a", "#ffe9a8"],
    "cuarto": ["#5a2a3a", "#1a0a18", "#ff6a9a"],
    "cuadricula": ["#1f6fd0", "#0d3b82", "#7fb6ff"],
    "espacio": ["#0b0f2a", "#000008", "#ffffff"],
    "degradado": ["#7c5cff", "#101030", "#ffffff"],
    "color": ["#202030", "#202030", "#ffffff"],
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s).lower())
    return re.sub(r"[^a-z0-9]+", "", "".join(c for c in s if unicodedata.category(c) != "Mn"))


# ----------------------------------------------------------------------------- fondos
class Backdrop:
    def __init__(self, kind: str, colors: list, w: int, h: int, seed: int = 0):
        self.kind, self.w, self.h = kind if kind in BG_CHOICES else "degradado", w, h
        base = DEFAULT_COLORS[self.kind]
        cs = [parse_color(c, parse_color(base[i % len(base)])) for i, c in enumerate((colors or []) + base[len(colors or []):])]
        self.c1, self.c2, self.c3 = cs[0], cs[1], cs[2]
        self.rnd = random.Random(seed + 11)
        self.static = self._build_static()
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        self.vig = (1 - 0.42 * (((xx - w / 2) / (w * 0.62)) ** 2 + ((yy - h * 0.48) / (h * 0.62)) ** 2)).clip(0.45, 1)[..., None]
        self.dust = [(self.rnd.random(), self.rnd.random(), self.rnd.random() * 6.28, self.rnd.uniform(1.5, 5.0), self.rnd.uniform(0.01, 0.04))
                     for _ in range(46)]
        if self.kind == "olas":
            hw, hh = w // 2, h // 2
            rs = np.random.RandomState(seed + 5)
            pts = rs.rand(150, 2).astype(np.float32) * [hw, hh]
            self.hy, self.hx = np.mgrid[0:hh, 0:hw].astype(np.float32)
            # deformación para bordes irregulares
            wx = self.hx + 9 * np.sin(self.hy / 23.0) + 6 * np.sin(self.hy / 9.0 + self.hx / 31.0)
            wy = self.hy + 9 * np.sin(self.hx / 27.0) + 6 * np.sin(self.hx / 11.0)
            d1 = np.full((hh, hw), 1e9, np.float32)
            d2 = np.full((hh, hw), 1e9, np.float32)
            for px, py in pts:
                dd = np.sqrt((wx - px) ** 2 + (wy - py) ** 2)
                d2 = np.minimum(d2, np.maximum(d1, dd))
                d1 = np.minimum(d1, dd)
            edge = np.clip(1 - (d2 - d1) / 4.5, 0, 1)
            self.tex = cv2.GaussianBlur(edge, (0, 0), 1.2) * 0.9
            self.cell = (np.clip(d1 / 60.0, 0, 1))  # sombreado suave dentro de cada celda
        self.extra = None
        if self.kind == "niebla":
            n = np.random.RandomState(seed).rand(h // 8 + 2, w // 8 + 2).astype(np.float32)
            n = cv2.GaussianBlur(n, (0, 0), 6)
            n = (n - n.min()) / (n.max() - n.min() + 1e-6)
            self.extra = cv2.resize(n, (w + 160, h + 160))
        elif self.kind == "espacio":
            self.stars = [(self.rnd.random() * w, self.rnd.random() * h, self.rnd.random() * 6.28, self.rnd.uniform(1.5, 4.5))
                          for _ in range(160)]

    def _build_static(self) -> np.ndarray:
        w, h, k = self.w, self.h, self.kind
        if k == "color":
            return np.full((h, w, 3), self.c1, np.uint8)
        g = np.asarray(gradient_image(w, h, self.c1, self.c2).convert("RGB"), np.uint8).copy()
        if k == "ladrillos":
            im = g.copy()
            bw, bh = int(w * 0.17), int(w * 0.085)
            rnd = random.Random(2)
            for r_, y in enumerate(range(0, h, bh)):
                off = (bw // 2) if r_ % 2 else 0
                for x in range(-off, w, bw):
                    v = rnd.uniform(0.88, 1.12)
                    col = np.array(self.c1, np.float32) * v
                    x0, x1, y0, y1 = max(0, x + 4), min(w, x + bw - 4), y + 4, min(h, y + bh - 4)
                    if x1 <= x0 or y1 <= y0:
                        continue
                    im[y0:y1, x0:x1] = col
                    im[y0:y0 + 6, x0:x1] = np.minimum(col * 1.35, 255)
                    im[y1 - 7:y1, x0:x1] = col * 0.65
            return im
        if k == "azulejos":
            tile = int(w * 0.105)
            im = g.copy()
            top, wall_h = int(h * 0.02), int(h * 0.72)
            for y in range(0, wall_h, tile):
                for x in range(0, w, tile):
                    sh = 0.9 + 0.1 * ((x // tile + y // tile) % 2)
                    col = np.array(self.c1, np.float32) * sh
                    im[y + 3:y + tile - 3, x + 3:x + tile - 3] = col
                    im[y + 3:y + 12, x + 3:x + tile - 3] = np.minimum(col * 1.18, 255)
            # franja roja y blanca
            y0 = int(h * 0.075)
            for x in range(0, w, tile):
                col = (200, 40, 50) if (x // tile) % 2 == 0 else (240, 232, 214)
                im[y0:y0 + int(tile * 0.5), x:x + tile] = col
            vig = np.linspace(0.55, 1.0, h)[:, None, None]
            im = (im * vig).astype(np.uint8)
            return im
        if k == "rayos":
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            ang = np.arctan2(xx - w / 2, yy + h * 0.1)
            ray = (np.sin(ang * 14) > 0).astype(np.float32) * 0.18
            fall = np.clip(1 - yy / (h * 0.9), 0, 1)
            col = np.array(self.c3, np.float32)
            g = np.clip(g + (ray * fall)[..., None] * col * 0.5, 0, 255).astype(np.uint8)
            floor = int(h * 0.72)
            g[floor:] = (g[floor:] * 0.55 + np.array(self.c2, np.float32) * 0.2).astype(np.uint8)
            return g
        if k == "cuarto":
            im = g.copy()
            for x in range(0, w, int(w * 0.09)):
                im[:int(h * 0.7), x:x + int(w * 0.045)] = (im[:int(h * 0.7), x:x + int(w * 0.045)] * 0.82).astype(np.uint8)
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            glow = np.exp(-(((xx - w / 2) / (w * 0.35)) ** 2 + ((yy - h * 0.72) / (h * 0.1)) ** 2))
            im = np.clip(im + glow[..., None] * np.array(self.c3, np.float32) * 0.8, 0, 255).astype(np.uint8)
            return im
        if k == "cuadricula":
            im = g.copy()
            step = int(w * 0.085)
            line = np.array(self.c3, np.float32)
            for x in range(0, w, step):
                im[:, x:x + 2] = (im[:, x:x + 2] * 0.5 + line * 0.5).astype(np.uint8)
            for y in range(0, h, step):
                im[y:y + 2] = (im[y:y + 2] * 0.5 + line * 0.5).astype(np.uint8)
            return im
        if k == "degradado":
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            v = 1 - 0.35 * (((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
            return np.clip(g * v[..., None], 0, 255).astype(np.uint8)
        return g

    def _waves(self, t: float) -> np.ndarray:
        w, h = self.w // 2, self.h // 2
        top = np.array(self.c2, np.float32)
        mid = np.array(self.c1, np.float32)
        lite = np.array(self.c3, np.float32)
        yy = self.hy
        v = (yy / h)[..., None]
        im = top * (1 - 0.15 * v) + mid * 0.18 * v
        im = im * (1 - self.tex[..., None] * 0.10)  # celdas tenues también en el fondo
        xs = np.arange(w, dtype=np.float32)
        n_l = 4
        for i in range(n_l):
            y0 = h * (0.15 + 0.22 * i)
            amp = h * (0.035 + 0.006 * i)
            ph = t * (0.40 + 0.10 * i) * (1 if i % 2 == 0 else -1) + i * 1.9
            crest = y0 + amp * np.sin(xs / w * 6.28 * 1.1 + ph) + amp * 0.35 * np.sin(xs / w * 6.28 * 2.3 + ph * 1.5 + i)
            d = yy - crest[None, :]
            inside = np.clip(d + 0.5, 0, 1)[..., None]
            k = i / (n_l - 1)
            base = mid * (0.55 + 0.55 * k) + top * (0.3 * (1 - k))
            deep = np.clip(d / (h * 0.45), 0, 1)[..., None]
            glow = np.exp(-np.clip(d, 0, None) / (h * 0.05))[..., None]
            col = base * (1 - 0.32 * deep) + lite * (0.22 * glow)
            col = col * (1 - self.tex[..., None] * (0.22 + 0.05 * k))      # líneas de celdas oscuras
            col = col * (1 + (self.cell[..., None] - 0.5) * 0.12)
            # membrana translúcida: doble borde claro
            rim1 = np.exp(-np.abs(d - 1.5) / 2.0)[..., None] * lite * 0.95
            rim2 = np.exp(-np.abs(d - 11.0) / 1.6)[..., None] * lite * 0.45
            shadow_above = np.exp(-np.clip(-d, 0, None) / (h * 0.05))[..., None] * 0.35
            im = im * (1 - shadow_above * (d[..., None] < 0))
            im = im * (1 - inside) + col * inside
            im = im + (rim1 + rim2) * 0.6
        out = np.clip(im, 0, 255).astype(np.uint8)
        return cv2.resize(out, (self.w, self.h), interpolation=cv2.INTER_LINEAR)

    def frame(self, t: float) -> np.ndarray:
        k, w, h = self.kind, self.w, self.h
        if k == "olas":
            im = self._waves(t)
        elif k == "niebla":
            ox, oy = int(80 + 60 * math.sin(t * 0.4)), int(80 + 60 * math.cos(t * 0.33))
            n = self.extra[oy:oy + h, ox:ox + w]
            col = np.array(self.c3, np.float32)
            im = np.clip(self.static + (n[..., None] ** 2) * col * 0.55, 0, 255).astype(np.uint8)
        elif k == "espacio":
            im = self.static.copy()
            for x, y, ph, r in self.stars:
                a = 0.5 + 0.5 * math.sin(t * 2 + ph)
                cv2.circle(im, (int(x), int(y)), max(1, int(r * (0.5 + a))), tuple(int(c * (0.4 + 0.6 * a)) for c in self.c3), -1, cv2.LINE_AA)
        else:
            im = self.static
        im = (im.astype(np.float32) * self.vig).astype(np.uint8)
        if k in ("olas", "ladrillos", "niebla", "rayos", "cuarto", "degradado"):
            ov = im.copy()
            for fx, fy, ph, r, sp in self.dust:
                a = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * 1.5 + ph))
                cx, cy = int(((fx + math.sin(t * 0.3 + ph) * 0.02) % 1) * w), int(((fy - sp * t) % 1) * h)
                cv2.circle(ov, (cx, cy), max(1, int(r * 1.4)), tuple(int(c) for c in (np.array(self.c3) * 0.6 + 120 * a)), -1, cv2.LINE_AA)
            im = cv2.addWeighted(ov, 0.45, im, 0.55, 0)
        return im


# ----------------------------------------------------------------------------- escena
def _split_anim(a) -> list[str]:
    if isinstance(a, (list, tuple)):
        return [str(x).strip() for x in a]
    return [x.strip() for x in str(a or "").replace(",", "+").split("+") if x.strip()]


class VectorScene(Scene):
    type = "vector"

    def default_duration(self) -> float:
        return 6.0

    def prepare(self) -> None:
        super().prepare()
        if self.captions:
            self.captions.y = float(self.spec.get("caption_y", 0.12)) * self.ctx.h
            self.captions.style = self.spec.get("caption_style", "caja")
            if self.captions.style == "caja":
                self.captions.size = int(self.spec.get("caption_size", 66))
                self.captions.font = "bold"

    def prepare_visual(self) -> None:
        s, c = self.spec, self.ctx
        cols = s.get("bg_colors") or []
        if isinstance(cols, str):
            cols = [x.strip() for x in cols.split(",") if x.strip()]
        self.backdrop = Backdrop(s.get("bg", "olas"), cols, c.w, c.h, seed=self.index)
        layers = s.get("layers") or []
        if isinstance(layers, str):
            try:
                layers = json.loads(layers) if layers.strip() else []
            except json.JSONDecodeError as e:
                self.warnings.append(f"Las capas no son JSON válido: {e}")
                layers = []
        self.layers = []
        for i, L in enumerate(layers):
            if not isinstance(L, dict) or L.get("asset") not in ASSETS:
                self.warnings.append(f"Capa {i + 1}: elemento «{(L or {}).get('asset') if isinstance(L, dict) else L}» desconocido")
                continue
            self.layers.append(self._norm_layer(L, i))
        self.layers.sort(key=lambda d: (d["z"], d["i"]))

    # ---- tiempos por palabra --------------------------------------------
    def _cue(self, v, default=None):
        if v is None or v == "":
            return default
        if isinstance(v, (int, float)):
            return float(v)
        txt = str(v).strip()
        try:
            return float(txt)
        except ValueError:
            pass
        nth = 1
        m = re.match(r"^(.*)#(\d+)$", txt)
        if m:
            txt, nth = m.group(1), int(m.group(2))
        target = _norm(txt)
        seen = 0
        for w in self.words:
            if _norm(w[0]) == target:
                seen += 1
                if seen == nth:
                    return float(w[1])
        self.warnings.append(f"No encontré la palabra «{txt}» en la narración para sincronizar.")
        return default

    def _norm_layer(self, L: dict, i: int) -> dict:
        d = dict(L)
        d["i"] = i
        d["start"] = self._cue(L.get("at"), 0.0) or 0.0
        e = self._cue(L.get("out"), None)
        d["end"] = e
        d["anim_l"] = _split_anim(L.get("anim", "pop"))
        d["z"] = float(L.get("z", i))
        d["count"] = max(1, int(L.get("count", 1)))
        d["seed"] = int(L.get("seed", i * 17 + 3))
        d["params"] = {k: v for k, v in L.items() if k not in (
            "asset", "x", "y", "w", "rot", "at", "out", "anim", "z", "count", "spread", "seed", "layout", "cols", "stagger",
            "alpha", "flip", "shadow", "value_from", "value_to", "value_dur", "speed", "amp", "w_var")}
        return d

    # ---- dibujo ------------------------------------------------------------
    def draw(self, t: float) -> Image.Image:
        c = self.ctx
        img = Image.fromarray(self.backdrop.frame(t), "RGB").convert("RGBA")
        for L in self.layers:
            self._draw_layer(img, L, t)
        out = img.convert("RGB")
        cam = self.spec.get("camera", "push")
        if cam and cam != "none":
            p = clamp(t / max(self.duration, 0.1))
            sc = {"push": 1 + 0.07 * p, "pull": 1.07 - 0.07 * p}.get(cam, 1.05)
            ox = {"pan_left": -0.03 + 0.06 * p, "pan_right": 0.03 - 0.06 * p}.get(cam, 0.0)
            cw, ch = c.w / sc, c.h / sc
            x0 = (c.w - cw) / 2 + ox * c.w
            x0 = min(max(0, x0), c.w - cw)
            out = out.crop((int(x0), int((c.h - ch) / 2), int(x0 + cw), int((c.h - ch) / 2 + ch))).resize((c.w, c.h), Image.BILINEAR)
        return out

    def _positions(self, L: dict):
        n, c = L["count"], self.ctx
        x, y = float(L.get("x", 0.5)), float(L.get("y", 0.5))
        sp = L.get("spread") or [x - 0.15, y - 0.15, x + 0.15, y + 0.15]
        rnd = random.Random(L["seed"])
        out = []
        layout = L.get("layout", "random" if n > 1 else "single")
        cols = int(L.get("cols", max(1, round(math.sqrt(n)))))
        rows = max(1, math.ceil(n / cols))
        for k in range(n):
            if layout == "single" or n == 1:
                px, py = x, y
            elif layout == "grid":
                r_, c_ = divmod(k, cols)
                px = sp[0] + (sp[2] - sp[0]) * ((c_ + (0.5 if r_ % 2 else 0.0)) / max(1, cols - 1 + (0.5 if rows > 1 else 0)))
                py = sp[1] + (sp[3] - sp[1]) * (r_ / max(1, rows - 1))
                px += rnd.uniform(-0.012, 0.012)
            elif layout == "line":
                f = k / max(1, n - 1)
                px, py = sp[0] + (sp[2] - sp[0]) * f, sp[1] + (sp[3] - sp[1]) * f
            else:
                px, py = rnd.uniform(sp[0], sp[2]), rnd.uniform(sp[1], sp[3])
            out.append((px, py, rnd.random() * 6.28, rnd.uniform(0.75, 1.25)))
        return out

    def _draw_layer(self, img: Image.Image, L: dict, t: float) -> None:
        c = self.ctx
        start, end = L["start"], L["end"]
        if t < start:
            return
        alpha_out = 1.0
        if end is not None:
            if t > end + 0.35:
                return
            alpha_out = 1 - seg(t, end, end + 0.35, "linear")
        anims = L["anim_l"]
        speed = float(L.get("speed", 1.0))
        base_w = float(L.get("w", 0.2)) * c.w
        pos = L.setdefault("_pos", self._positions(L))
        stagger = float(L.get("stagger", 0.05 if L["count"] > 1 else 0.0))
        spread = L.get("spread") or [0, 0, 1, 1]
        for k, (px, py, ph, sv) in enumerate(pos):
            lt = t - start - k * stagger
            if lt < 0:
                continue
            x, y = px * c.w, py * c.h
            rot = float(L.get("rot", 0))
            sc = sv if L["count"] > 1 and "nosize" not in anims else 1.0
            sc *= 1.0
            al = float(L.get("alpha", 1.0)) * alpha_out
            wob = lt * speed
            amp = float(L.get("amp", 1.0))
            for a in anims:
                if a == "pop":
                    q = seg(lt, 0, 0.5, "out_back")
                    sc *= q
                    al *= clamp(q * 3)
                elif a == "fade":
                    al *= seg(lt, 0, 0.6, "linear")
                elif a == "grow":
                    sc *= seg(lt, 0, 1.2, "out_cubic")
                elif a in ("slide_left", "slide_right", "slide_up", "slide_down"):
                    q = 1 - seg(lt, 0, 0.6, "out_cubic")
                    dx = {"slide_left": -1, "slide_right": 1}.get(a, 0) * c.w * 0.7 * q
                    dy = {"slide_up": 1, "slide_down": -1}.get(a, 0) * c.h * 0.5 * q
                    x += dx
                    y += dy
                elif a == "drop":
                    q = seg(lt, 0, 0.8, "out_back")
                    y -= (1 - q) * c.h * 0.6
                    al *= clamp(lt * 6)
                elif a == "float":
                    y += math.sin(wob * 1.6 + ph) * c.h * 0.012 * amp
                    x += math.sin(wob * 1.1 + ph * 2) * c.w * 0.006 * amp
                    rot += math.sin(wob * 1.3 + ph) * 3 * amp
                elif a == "bounce":
                    y -= abs(math.sin(wob * 3.2 + ph)) * c.h * 0.04 * amp
                elif a == "shake":
                    x += math.sin(wob * 38 + ph) * c.w * 0.006 * amp
                    rot += math.sin(wob * 31) * 2.5 * amp
                elif a == "pulse":
                    sc *= 1 + 0.07 * amp * math.sin(wob * 4 + ph)
                elif a == "spin":
                    rot += wob * 90 * amp + math.degrees(ph) * (L["count"] > 1)
                elif a == "wobble":
                    rot += math.sin(wob * 2.6 + ph) * 9 * amp
                elif a == "drift":
                    vx = math.cos(ph) * 0.05 * amp
                    vy = math.sin(ph * 1.7) * 0.04 * amp
                    bw, bh = max(spread[2] - spread[0], 0.05), max(spread[3] - spread[1], 0.05)
                    x = (spread[0] + ((px - spread[0] + vx * lt) % bw)) * c.w
                    y = (spread[1] + ((py - spread[1] + vy * lt) % bh)) * c.h
                    rot += math.sin(wob * 1.2 + ph) * 12
                elif a == "fall":
                    y = ((py + 0.12 * lt * amp) % 1.2 - 0.1) * c.h
                elif a == "rise":
                    y = ((py - 0.1 * lt * amp) % 1.2 - 0.1) * c.h
                elif a == "blink":
                    al *= 0.5 + 0.5 * math.sin(wob * 6 + ph) ** 2
            if al <= 0.01 or sc <= 0.02:
                continue
            params = dict(L["params"])
            if L["count"] > 1:
                params.setdefault("var", k)
            if "value_from" in L:
                vd = float(L.get("value_dur", 1.5))
                v = lerp(float(L["value_from"]), float(L.get("value_to", L["value_from"])), ease("in_out_cubic", clamp(lt / vd)))
                params["value"] = round(v * 4) / 4
            wpx = int(round(base_w / 6.0) * 6)
            spr = sprite(L["asset"], wpx, params, L.get("shadow", L["asset"] not in ("texto", "hielo", "banda", "olor", "agua")))
            if L.get("flip"):
                spr = spr.transpose(Image.FLIP_LEFT_RIGHT)
            ws = max(2, int(spr.width * sc * base_w / max(wpx, 1)))
            hs = max(2, int(spr.height * sc * base_w / max(wpx, 1)))
            if (ws, hs) != spr.size:
                spr = spr.resize((ws, hs), Image.BILINEAR)
            if abs(rot) > 0.3:
                spr = spr.rotate(-rot, Image.BICUBIC, expand=True)
            if al < 0.99:
                a_ch = spr.getchannel("A").point([int(i * al) for i in range(256)])
                spr = spr.copy()
                spr.putalpha(a_ch)
            self._clip_paste(img, spr, x, y)

    @staticmethod
    def _clip_paste(img, spr, x, y) -> None:
        px, py = int(x - spr.width / 2), int(y - spr.height / 2)
        if px >= img.width or py >= img.height or px + spr.width <= 0 or py + spr.height <= 0:
            return
        img.paste(spr, (px, py), spr)


# ----------------------------------------------------------------------------- instrucciones para IA
def ai_prompt() -> str:
    lib = "\n".join(f"- {k}: {d[2]}. Parámetros: {d[3] or '—'}" for k, d in ASSETS.items())
    return f"""Eres director de animación para videos educativos verticales de YouTube Shorts en español. Convierte el guion que te daré en una lista de ESCENAS en JSON. Cada escena dura unas 2-6 s y cubre una o dos frases del guion.

Formato de cada escena (responde SOLO un arreglo JSON, sin texto extra):
{{"type":"vector","bg":"olas|azulejos|niebla|rayos|cuarto|cuadricula|espacio|degradado|color",
 "bg_colors":["#hex1","#hex2","#hex3"],  // opcional: fondo claro, fondo oscuro, acento
 "narration":"frase(s) que se dicen en esta escena",
 "camera":"push|pull|pan_left|pan_right",  // opcional
 "layers":[ ...capas... ]}}

Cada capa: {{"asset":"nombre","x":0-1,"y":0-1 (centro, fracción del alto/ancho),"w":0.05-1 (ancho como fracción del ancho de pantalla),
 "at":"palabra de la narración que lo hace aparecer" (o segundos), "out":"palabra o segundos en que desaparece" (opcional),
 "anim":"pop+float" (entradas: pop, fade, grow, slide_left, slide_right, slide_up, slide_down, drop; movimiento continuo: float, bounce, shake, pulse, spin, wobble, drift, fall, rise, blink),
 "count":N con "spread":[x0,y0,x1,y1] y "layout":"random|grid|line" para enjambres/multitudes, "rot":grados,"flip":true,"z":orden (mayor = encima),
 más los parámetros propios del elemento}}.
Para el medidor puedes animar la aguja con "value_from", "value_to" y "value_dur".

Reglas: usa "at" con palabras EXACTAS de la narración para sincronizar la aparición con la voz. Los fondos "azulejos" y los elementos "banda" y "hielo" sirven para escenas de tienda/pescadería (banda en y≈0.9). Pon 2-5 capas por escena, con un elemento protagonista grande (w 0.4-0.8) y detalles. Varía fondos y cámaras entre escenas. Mantén las capas dentro de la pantalla (x,y entre 0.1 y 0.9, deja libre la franja y<0.2 para los subtítulos).

Elementos disponibles:
{lib}
"""
