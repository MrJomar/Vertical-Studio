"""Animación vectorial por capas: fondos, personajes y objetos con animaciones sincronizadas a la voz."""
from __future__ import annotations

import json
import math
import random
import re
import unicodedata

import cv2
import numpy as np
from PIL import Image, ImageDraw

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

BG_CHOICES = ["musculo", "cuerpo", "olas", "ladrillos", "azulejos", "niebla", "rayos", "cuarto", "cuadricula", "espacio", "degradado", "color"]
CAMERAS = ["", "push", "pull", "push_fuerte", "drift", "pan_left", "pan_right"]

DEFAULT_COLORS = {
    "musculo": ["#b0243a", "#3a0a14", "#ff7a86"],
    "cuerpo": ["#16306a", "#050a1e", "#5fb4ff"],
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
        if k == "musculo":
            im = g.copy()
            rnd = np.random.RandomState(7)
            lay = np.zeros((h, w, 3), np.float32)
            msk = np.zeros((h, w), np.float32)
            for i in range(70):
                x0 = rnd.uniform(-0.1, 1.1) * w
                th = int(rnd.uniform(0.012, 0.05) * w)
                ph, amp = rnd.uniform(0, 6.28), rnd.uniform(0.02, 0.05) * w
                pts = np.array([[x0 + amp * math.sin(y / h * 3.14 * rnd.uniform(0.6, 1.1) + ph) + (y - h / 2) * 0.08, y] for y in range(-20, h + 90, 90)], np.int32)
                tone = rnd.uniform(0.7, 1.35)
                cv2.polylines(lay, [pts], False, tuple(float(c) * tone for c in self.c1), th, cv2.LINE_AA)
                cv2.polylines(msk, [pts], False, 1.0, th, cv2.LINE_AA)
                cv2.polylines(lay, [pts + [int(th * 0.2), 0]], False, tuple(min(255., c * 1.7) for c in self.c3), max(1, th // 6), cv2.LINE_AA)
            msk = cv2.GaussianBlur(msk, (0, 0), 2)[..., None]
            lay = cv2.GaussianBlur(lay, (0, 0), 1.5)
            im = (im * (1 - msk) * 0.55 + lay * msk + im * 0.0).clip(0, 255).astype(np.uint8)
            return im
        if k == "cuerpo":
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            glow = np.exp(-(((xx - w * 0.5) / (w * 0.7)) ** 2 + ((yy - h * 0.3) / (h * 0.35)) ** 2))
            im = g.astype(np.float32) + glow[..., None] * np.array(self.c3, np.float32) * 0.22
            step = int(w * 0.09)
            for x in range(0, w, step):
                im[:, x:x + 1] = im[:, x:x + 1] * 0.8 + np.array(self.c3, np.float32) * 0.2
            for y in range(0, h, step):
                im[y:y + 1] = im[y:y + 1] * 0.8 + np.array(self.c3, np.float32) * 0.2
            fl = int(h * 0.88)
            im[fl:] = im[fl:] * 0.6
            im[fl:fl + 3] = np.array(self.c3, np.float32) * 0.8
            return im.clip(0, 255).astype(np.uint8)
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



_shape_cache: dict = {}


def _shape_points(shape: str, n: int, seed: int) -> list:
    """Puntos (u,v en -0.5..0.5) que dibujan una figura: cara, corazon, circulo, estrella, texto:ABC."""
    key = (shape, n, seed)
    if key in _shape_cache:
        return _shape_cache[key]
    from PIL import ImageDraw as _D
    S = 220
    m = Image.new("L", (S, S), 0)
    d = _D.Draw(m)
    sh = shape.lower()
    if sh.startswith("texto:"):
        from .core import get_font
        txt = shape[6:]
        f = get_font("display", 150)
        bb = d.textbbox((0, 0), txt, font=f)
        sc = min(1.0, (S * 0.94) / max(1, bb[2] - bb[0]))
        if sc < 1:
            f = get_font("display", max(20, int(150 * sc)))
            bb = d.textbbox((0, 0), txt, font=f)
        d.text(((S - (bb[2] - bb[0])) / 2 - bb[0], (S - (bb[3] - bb[1])) / 2 - bb[1]), txt, font=f, fill=255)
    elif sh == "corazon":
        pts = []
        for k in range(200):
            t = k / 200 * 2 * math.pi
            pts.append((S / 2 + 6.2 * 16 * math.sin(t) ** 3 * 0.88,
                        S * 0.47 - 6.2 * (13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)) * 0.88))
        d.polygon(pts, fill=255)
    elif sh == "estrella":
        pts = []
        for k in range(10):
            r = S * (0.48 if k % 2 == 0 else 0.2)
            a = -math.pi / 2 + k * math.pi / 5
            pts.append((S / 2 + r * math.cos(a), S / 2 + r * math.sin(a)))
        d.polygon(pts, fill=255)
    elif sh == "circulo":
        d.ellipse([8, 8, S - 8, S - 8], outline=255, width=22)
    else:  # cara
        d.ellipse([8, 8, S - 8, S - 8], outline=255, width=16)
        d.ellipse([S * 0.28, S * 0.3, S * 0.42, S * 0.5], fill=255)
        d.ellipse([S * 0.58, S * 0.3, S * 0.72, S * 0.5], fill=255)
        d.arc([S * 0.25, S * 0.35, S * 0.75, S * 0.78], 20, 160, fill=255, width=16)
    arr = np.asarray(m) > 128
    ys, xs = np.nonzero(arr)
    rnd = random.Random(seed)
    idx = list(range(len(xs)))
    rnd.shuffle(idx)
    pts, r = [], S * 0.9 / max(2.0, math.sqrt(n)) * 0.78
    while len(pts) < n:
        pts = []
        for i in idx:
            x, y = xs[i], ys[i]
            if all((x - a) ** 2 + (y - b) ** 2 >= r * r for a, b in pts):
                pts.append((x, y))
                if len(pts) >= n:
                    break
        r *= 0.88
        if r < 1.5:
            while len(pts) < n:
                i = rnd.choice(idx)
                pts.append((xs[i], ys[i]))
    out = [((x - S / 2) / S, (y - S / 2) / S) for x, y in pts]
    _shape_cache[key] = out
    return out


FX_CHOICES = ["humo", "bokeh", "bokeh_frente", "corazones", "brillos", "nieve", "burbujas", "polvo_luz"]


class _FX:
    """Partículas ambientales baratas (se dibujan a un cuarto de resolución y se suben)."""

    def __init__(self, names: list, color, w: int, h: int, seed: int):
        self.names, self.w, self.h = names, w, h
        self.col = tuple(color[:3])
        r = random.Random(seed + 91)
        self.p = {n: [(r.random(), r.random(), r.random() * 6.28, r.uniform(0.6, 1.4)) for _ in range(
            {"humo": 7, "bokeh": 16, "bokeh_frente": 5, "corazones": 11, "brillos": 14, "nieve": 60, "burbujas": 14, "polvo_luz": 30}[n])]
            for n in names}

    def draw(self, img: Image.Image, t: float, front: bool) -> None:
        w, h = self.w, self.h
        q = 4
        ov = Image.new("RGBA", (w // q, h // q), (0, 0, 0, 0))
        dr = ImageDraw.Draw(ov)
        blur = 0.0
        col = self.col
        for n in self.names:
            if (n == "bokeh_frente") != front:
                continue
            for fx, fy, ph, sz in self.p[n]:
                if n == "humo":
                    x = ((fx + 0.03 * math.sin(t * 0.3 + ph) + t * 0.01 * sz) % 1.3 - 0.15) * w
                    y = (0.2 + 0.7 * fy + 0.04 * math.sin(t * 0.4 + ph)) * h
                    r = w * 0.32 * sz
                    dr.ellipse([(x - r) / q, (y - r * 0.6) / q, (x + r) / q, (y + r * 0.6) / q], fill=col + (46,))
                    blur = max(blur, 11)
                elif n in ("bokeh", "bokeh_frente"):
                    big = n == "bokeh_frente"
                    x = ((fx + 0.02 * math.sin(t * 0.4 + ph)) % 1) * w
                    y = ((fy - 0.018 * t * sz) % 1.1 - 0.05) * h
                    r = w * (0.09 if big else 0.032) * sz
                    a = int((70 if big else 55) * (0.6 + 0.4 * math.sin(t * 1.2 + ph)))
                    dr.ellipse([(x - r) / q, (y - r) / q, (x + r) / q, (y + r) / q], fill=tuple(min(255, int(c * 0.5 + 130)) for c in col) + (a,))
                    blur = max(blur, 5 if big else 1.6)
                elif n == "nieve":
                    x = ((fx + 0.03 * math.sin(t * 0.8 + ph)) % 1) * w
                    y = ((fy + 0.09 * t * sz) % 1.05) * h
                    r = w * 0.006 * sz
                    dr.ellipse([(x - r) / q, (y - r) / q, (x + r) / q, (y + r) / q], fill=(255, 255, 255, 190))
                elif n == "polvo_luz":
                    x = ((fx + 0.02 * math.sin(t * 0.5 + ph)) % 1) * w
                    y = ((fy - 0.02 * t * sz) % 1.05) * h
                    r = w * 0.004 * sz
                    a = int(220 * (0.3 + 0.7 * math.sin(t * 2 + ph) ** 2))
                    dr.ellipse([(x - r) / q, (y - r) / q, (x + r) / q, (y + r) / q], fill=(255, 250, 220, a))
        if blur:
            ov = ov.filter(ImageFilter.GaussianBlur(blur / q * 1.4))
        ov = ov.resize((w, h), Image.BILINEAR)
        img.alpha_composite(ov)
        if front:
            return
        for n in self.names:
            if n == "corazones":
                for fx, fy, ph, sz in self.p[n]:
                    x = (fx + 0.03 * math.sin(t * 1.2 + ph)) * w
                    y = ((fy - 0.07 * t * sz) % 1.2 - 0.1) * h
                    a = clamp(1 - abs(y / h - 0.5) * 1.1) * 0.85
                    sp = sprite("corazon", int(w * 0.04 * sz) // 4 * 4 + 4, {"color": "#ff7aa8"}, False)
                    sp = sp.copy()
                    sp.putalpha(sp.getchannel("A").point([int(i * a) for i in range(256)]))
                    img.alpha_composite(sp, (int(x - sp.width / 2), int(y - sp.height / 2))) if 0 <= x < w and 0 <= y < h else None
            elif n == "brillos":
                for fx, fy, ph, sz in self.p[n]:
                    a = max(0.0, math.sin(t * 2.2 + ph)) ** 3
                    if a < 0.05:
                        continue
                    x, y, r = fx * w, fy * h, w * 0.022 * sz * (0.5 + a)
                    d2 = ImageDraw.Draw(img)
                    c4 = (255, 255, 235, int(235 * a))
                    d2.polygon([(x, y - r), (x + r * 0.22, y - r * 0.22), (x + r, y), (x + r * 0.22, y + r * 0.22), (x, y + r),
                                (x - r * 0.22, y + r * 0.22), (x - r, y), (x - r * 0.22, y - r * 0.22)], fill=c4)
            elif n == "burbujas":
                for fx, fy, ph, sz in self.p[n]:
                    x = (fx + 0.02 * math.sin(t * 1.1 + ph)) * w
                    y = ((fy - 0.06 * t * sz) % 1.15 - 0.08) * h
                    d = int(w * 0.05 * sz) // 2 * 2 + 4
                    sp = sprite("burbuja", d, {}, False)
                    if 0 <= x < w and 0 <= y < h:
                        img.alpha_composite(sp, (int(x - d / 2), int(y - d / 2)))


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
            self.captions.style = self.spec.get("caption_style", "suave")
            if self.captions.style in ("caja", "suave"):
                self.captions.size = int(self.spec.get("caption_size", 58 if self.captions.style == "suave" else 66))
                self.captions.font = "bold"
            if self.captions.style == "suave" and not self.spec.get("caption_upper", False):
                self.captions.groups = [[(w[0].lower(), w[1], w[2]) for w in g] for g in self.captions.groups]

    def prepare_visual(self) -> None:
        s, c = self.spec, self.ctx
        cols = s.get("bg_colors") or []
        if isinstance(cols, str):
            cols = [x.strip() for x in cols.split(",") if x.strip()]
        self.backdrop = Backdrop(s.get("bg", "olas"), cols, c.w, c.h, seed=self.index)
        fxn = s.get("fx") or ""
        fxl = [x.strip() for x in (fxn if isinstance(fxn, list) else str(fxn).replace("+", ",").split(",")) if x.strip() in FX_CHOICES]
        self.fx = _FX(fxl, parse_color(s.get("fx_color"), self.backdrop.c3) if s.get("fx_color") else self.backdrop.c3, c.w, c.h, self.index) if fxl else None
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
        d["form"] = self._cue(L.get("form"), d["start"]) if L.get("shape") else None
        d["react"] = self._cue(L.get("react"), None) if L.get("react") not in (None, "") else None
        d["params"] = {k: v for k, v in L.items() if k not in (
            "asset", "x", "y", "w", "rot", "at", "out", "anim", "z", "count", "spread", "seed", "layout", "cols", "stagger",
            "alpha", "flip", "shadow", "value_from", "value_to", "value_dur", "speed", "amp", "w_var",
            "blur", "rot_var", "glow", "shape", "form", "form_dur", "react", "rfrom", "rdist", "react_mood", "react_fade",
            "react_shrink", "mood_at", "mood_to")}
        return d

    # ---- dibujo ------------------------------------------------------------
    def draw(self, t: float) -> Image.Image:
        c = self.ctx
        img = Image.fromarray(self.backdrop.frame(t), "RGB").convert("RGBA")
        if self.fx:
            self.fx.draw(img, t, False)
        for L in self.layers:
            self._draw_layer(img, L, t)
        if self.fx:
            self.fx.draw(img, t, True)
        out = img.convert("RGB")
        cam = self.spec.get("camera", "push")
        if cam and cam != "none":
            p = clamp(t / max(self.duration, 0.1))
            e = ease("in_out_cubic", p)
            sc = {"push": 1 + 0.09 * e, "pull": 1.09 - 0.09 * e, "push_fuerte": 1 + 0.2 * e, "drift": 1.07}.get(cam, 1.05)
            ox = {"pan_left": -0.03 + 0.06 * e, "pan_right": 0.03 - 0.06 * e}.get(cam, 0.0)
            oy = 0.0
            if cam == "drift":
                ox, oy = 0.02 * math.sin(t * 0.7), 0.015 * math.cos(t * 0.55)
            cw, ch = c.w / sc, c.h / sc
            x0 = min(max(0, (c.w - cw) / 2 + ox * c.w), c.w - cw)
            y0 = min(max(0, (c.h - ch) / 2 + oy * c.h), c.h - ch)
            out = out.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((c.w, c.h), Image.BILINEAR)
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
            if L.get("rot_var"):
                rot += math.sin(ph * 12.9) * float(L["rot_var"])
            if L.get("shape"):
                tgt = L.get("_tgt")
                if tgt is None:
                    spx = L.get("spread") or [x / c.w - 0.3, y / c.h - 0.3, x / c.w + 0.3, y / c.h + 0.3]
                    side = min((spx[2] - spx[0]) * c.w, (spx[3] - spx[1]) * c.h)
                    cx0, cy0 = (spx[0] + spx[2]) / 2 * c.w, (spx[1] + spx[3]) / 2 * c.h
                    tgt = L["_tgt"] = [(cx0 + u * side, cy0 + v * side) for u, v in _shape_points(str(L["shape"]), L["count"], L["seed"])]
                qf = ease("in_out_cubic", clamp((t - (L["form"] or 0) - k * 0.012) / float(L.get("form_dur", 1.3))))
                tx, ty = tgt[k]
                x, y = lerp(x, tx, qf), lerp(y, ty, qf)
                rot = lerp(rot, 0.0, qf)
                if qf >= 1:
                    y += math.sin(t * 2.0 + ph) * c.h * 0.0025
            if L.get("react") is not None and L["react"] is not None and t >= L["react"]:
                rq = seg(t - L["react"], 0, 0.55, "out_cubic")
                fx0, fy0 = (L.get("rfrom") or [0.5, 0.5])
                dx, dy = x - fx0 * c.w, y - fy0 * c.h
                dn = math.hypot(dx, dy) or 1.0
                dist = float(L.get("rdist", 0.14)) * c.w
                x += dx / dn * dist * rq
                y += dy / dn * dist * rq
                x += math.sin((t - L["react"]) * 40 + ph) * c.w * 0.006 * (1 - rq)
                if L.get("react_shrink"):
                    sc *= 1 - float(L["react_shrink"]) * rq
                if L.get("react_fade"):
                    al *= 1 - seg(t - L["react"], 0.25, 1.1, "linear")
            if al <= 0.01 or sc <= 0.02:
                continue
            params = dict(L["params"])
            if L.get("react_mood") and L.get("react") is not None and t >= L["react"]:
                params["mood"] = L["react_mood"]
            if L["count"] > 1:
                params.setdefault("var", k)
            if "value_from" in L:
                vd = float(L.get("value_dur", 1.5))
                v = lerp(float(L["value_from"]), float(L.get("value_to", L["value_from"])), ease("in_out_cubic", clamp(lt / vd)))
                params["value"] = round(v * 4) / 4
            wpx = int(round(base_w / 6.0) * 6)
            spr = sprite(L["asset"], wpx, params, L.get("shadow", L["asset"] not in ("texto", "hielo", "banda", "olor", "agua", "svg")))
            if L.get("flip"):
                spr = spr.transpose(Image.FLIP_LEFT_RIGHT)
            ws = max(2, int(spr.width * sc * base_w / max(wpx, 1)))
            hs = max(2, int(spr.height * sc * base_w / max(wpx, 1)))
            if (ws, hs) != spr.size:
                spr = spr.resize((ws, hs), Image.BILINEAR)
            if abs(rot) > 0.3:
                spr = spr.rotate(-rot, Image.BICUBIC, expand=True)
            bl = float(L.get("blur", 0) or 0)
            if bl > 0:
                spr = spr.filter(ImageFilter.GaussianBlur(max(0.5, bl * spr.width * 0.05)))
            if L.get("glow"):
                gc = parse_color(L["glow"], (255, 255, 200))
                m = int(max(4, spr.width * 0.28))      # margen para que el aura no se corte en el borde del sprite
                pad = Image.new("L", (spr.width + 2 * m, spr.height + 2 * m), 0)
                pad.paste(spr.getchannel("A"), (m, m))
                ga = pad.filter(ImageFilter.GaussianBlur(max(2, spr.width * 0.09)))
                halo = Image.new("RGBA", pad.size, tuple(gc[:3]) + (0,))
                halo.putalpha(ga.point([min(255, int(i * 1.6 * al)) for i in range(256)]))
                self._clip_paste(img, halo, x, y)
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
def ai_prompt(style: str = "") -> str:
    lib = "\n".join(f"- {k}: {d[2]}. Parámetros: {d[3] or '—'}" for k, d in ASSETS.items())
    return f"""Eres director de animación para videos educativos verticales de YouTube Shorts en español. Convierte el guion que te daré en una lista de ESCENAS en JSON. Cada escena dura unas 2-6 s y cubre una o dos frases del guion.

Formato de cada escena (responde SOLO un arreglo JSON, sin texto extra):
{{"type":"vector","bg":"olas|azulejos|niebla|rayos|cuarto|cuadricula|espacio|musculo|cuerpo|degradado|color",
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

Funciones para dar riqueza visual (úsalas con criterio, 1-3 por escena):
- Escena: "fx":"humo,bokeh,bokeh_frente,corazones,brillos,nieve,burbujas,polvo_luz" (ambiente; bokeh_frente son manchas grandes desenfocadas por delante), "fx_color":"#hex".
- Capa: "blur":0.2-1 (desenfoca: úsalo en elementos grandes del primer plano para dar profundidad), "glow":"#hex" (aura luminosa), "rot_var":grados (cada copia de un enjambre gira distinto),
  "shape":"cara|corazon|circulo|estrella|texto:PALABRA" con "count" 30-80 y "spread":[x0,y0,x1,y1]: el enjambre se mueve y forma esa figura en la palabra indicada en "form" (con "form_dur" segundos),
  "react":"palabra" + "rfrom":[x,y] (punto de impacto, p. ej. donde cae la pastilla) + "rdist":0.1-0.3 + "react_mood":"scared" + "react_shrink":0-0.6 + "react_fade":true: los personajes reaccionan huyendo/encogiéndose/desapareciendo.
- Cámaras extra: "drift" (flotante), "push_fuerte".
Capas de ambiente: "humo" (verde para olores), "luz" (brillo bajo una puerta, con "h"), "burbuja_villano", "molecula".
Para escenas con mucho detalle: fondo + 2 capas grandes desenfocadas delante + protagonista nítido + 4-12 elementos pequeños detrás, y cambia de escena cada 2-4 s.

Reglas: usa "at" con palabras EXACTAS de la narración para sincronizar la aparición con la voz. Los fondos "azulejos" y los elementos "banda" y "hielo" sirven para escenas de tienda/pescadería (banda en y≈0.9). Pon 2-5 capas por escena, con un elemento protagonista grande (w 0.4-0.8) y detalles. Varía fondos y cámaras entre escenas. Mantén las capas dentro de la pantalla (x,y entre 0.1 y 0.9, deja libre la franja y<0.2 para los subtítulos).

Elementos disponibles:
{lib}
""" + (__import__("vstudio.styles", fromlist=["x"]).style_block(style) if style else "")
