"""Biblioteca de elementos vectoriales dibujados por código (sin descargas, sin licencias).

Cada elemento es una función (ancho_px, params) -> imagen RGBA. Se dibujan con suavizado y sombreado.
"""
from __future__ import annotations

import colorsys
import math
import random

import numpy as np
from PIL import Image, ImageDraw

from .core import get_font, parse_color, text_layer

SS = 3  # supermuestreo


def _c(v, default):
    return parse_color(v, default) if v is not None else default


def _shade(c, k):
    return tuple(int(max(0, min(255, x * k))) for x in c[:3])


def _canvas(w, h):
    return Image.new("RGBA", (int(w * SS), int(h * SS)), (0, 0, 0, 0))


def _fin(im, w, h):
    return im.resize((max(1, int(w)), max(1, int(h))), Image.LANCZOS)


def sphere(d, color, spec=0.6, dark=0.42, light=(-0.42, -0.52)):
    d = max(2, int(d))
    y, x = np.mgrid[0:d, 0:d].astype(np.float32)
    c = (d - 1) / 2
    nx, ny = (x - c) / (d / 2), (y - c) / (d / 2)
    rr = nx * nx + ny * ny
    nz = np.sqrt(np.clip(1 - rr, 0, 1))
    lx, ly = light
    lz = math.sqrt(max(0.05, 1 - lx * lx - ly * ly))
    diff = np.clip(nx * lx + ny * ly + nz * lz, 0, 1)
    shade = dark + (1 - dark) * diff
    sp = (diff ** 28) * spec
    col = np.array(color[:3], np.float32)
    rgb = col[None, None, :] * shade[..., None] + 255 * sp[..., None]
    a = np.clip((1 - np.sqrt(rr)) * d / 2, 0, 1)
    out = np.dstack([np.clip(rgb, 0, 255), a * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def pill3d(W, H, color, spec=0.55, dark=0.45, light=(-0.35, -0.55)):
    """Cápsula con sombreado volumétrico (cilindro con extremos redondeados)."""
    W, H = max(4, int(W)), max(4, int(H))
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    r = H / 2
    cxl = np.clip(x, r, W - r)
    nx, ny = (x - cxl) / r, (y - (H - 1) / 2) / r
    rr = nx * nx + ny * ny
    nz = np.sqrt(np.clip(1 - rr, 0, 1))
    lx, ly = light
    lz = math.sqrt(max(0.05, 1 - lx * lx - ly * ly))
    diff = np.clip(nx * lx + ny * ly + nz * lz, 0, 1)
    shade = dark + (1 - dark) * diff
    sp = (diff ** 30) * spec
    col = np.array(color[:3], np.float32)
    rgb = col[None, None, :] * shade[..., None] + 255 * sp[..., None]
    a = np.clip((1 - np.sqrt(rr)) * r, 0, 1)
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), a * 255]).astype(np.uint8), "RGBA")


def _aura(im, color, radius, strength=0.55):
    from PIL import ImageFilter
    pad = int(radius * 2)
    big = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
    a = Image.new("L", big.size, 0)
    a.paste(im.getchannel("A"), (pad, pad))
    a = a.filter(ImageFilter.GaussianBlur(radius)).point([int(i * strength) for i in range(256)])
    glow = Image.new("RGBA", big.size, tuple(color[:3]) + (0,))
    glow.putalpha(a)
    big.alpha_composite(glow)
    big.alpha_composite(im, (pad, pad))
    return big


def _face(dr, cx, cy, r, mood="neutral", eye=0.22, pupil=(20, 20, 30)):
    """Ojos y boca sobre una cara de radio r (coordenadas ya supermuestreadas)."""
    ex = r * 0.34
    ey = cy - r * 0.08
    er = r * eye
    for sx in (-1, 1):
        x = cx + sx * ex
        if mood == "happy":
            dr.arc([x - er, ey - er * 0.6, x + er, ey + er * 1.2], 200, 340, fill=pupil, width=max(2, int(r * 0.08)))
            continue
        dr.ellipse([x - er, ey - er * 1.1, x + er, ey + er * 1.1], fill=(255, 255, 255, 255))
        px = x + (0 if mood != "angry" else -sx * er * 0.15)
        dr.ellipse([px - er * 0.55, ey - er * 0.55, px + er * 0.55, ey + er * 0.7], fill=pupil + (255,))
        dr.ellipse([px - er * 0.25, ey - er * 0.45, px + er * 0.05, ey - er * 0.15], fill=(255, 255, 255, 255))
        if mood == "angry":
            dr.polygon([(x - er * 1.4, ey - er * 1.9 if sx < 0 else ey - er * 0.7),
                        (x + er * 1.4, ey - er * 0.7 if sx < 0 else ey - er * 1.9),
                        (x + er * 1.4, ey - er * 0.2), (x - er * 1.4, ey - er * 0.2)], fill=(40, 20, 50, 255))
    my = cy + r * 0.42
    mw = r * 0.34
    if mood == "happy":
        dr.arc([cx - mw, my - mw * 0.9, cx + mw, my + mw * 0.7], 20, 160, fill=pupil, width=max(2, int(r * 0.07)))
    elif mood == "angry":
        dr.arc([cx - mw, my, cx + mw, my + mw * 1.2], 200, 340, fill=pupil, width=max(2, int(r * 0.07)))
    elif mood == "sad":
        dr.arc([cx - mw, my, cx + mw, my + mw], 200, 340, fill=pupil, width=max(2, int(r * 0.06)))
    elif mood == "scared":
        dr.ellipse([cx - mw * 0.4, my - mw * 0.1, cx + mw * 0.4, my + mw * 0.7], fill=(60, 20, 30, 255))
    else:
        dr.line([cx - mw * 0.7, my + mw * 0.2, cx + mw * 0.7, my + mw * 0.2], fill=pupil, width=max(2, int(r * 0.06)))


def _paste_ss(base, sprite_ss, x, y):
    base.alpha_composite(sprite_ss, (int(x), int(y)))


# ---------------------------------------------------------------- personajes y criaturas
def a_esfera(w, p):
    col = _c(p.get("color"), (70, 110, 240))
    d = int(w)
    im = sphere(d, col)
    if p.get("mood", "neutral") != "none":
        big = _canvas(d, d)
        dr = ImageDraw.Draw(big)
        _face(dr, d * SS / 2, d * SS / 2, d * SS / 2, p.get("mood", "neutral"))
        im.alpha_composite(_fin(big, d, d))
    return im


def a_villano(w, p):
    """Bolita azul enmascarada con capa y brazos de esferas (estilo molécula)."""
    W, H = int(w), int(w * 1.0)
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    s = SS
    cape = _c(p.get("cape"), (120, 22, 40))
    cx = W * s / 2
    dr.polygon([(cx - W * s * 0.2, H * s * 0.4), (cx + W * s * 0.2, H * s * 0.4), (cx + W * s * 0.47, H * s * 0.94),
                (cx, H * s * 0.86), (cx - W * s * 0.47, H * s * 0.94)], fill=cape + (255,))
    dr.polygon([(cx - W * s * 0.2, H * s * 0.4), (cx - W * s * 0.05, H * s * 0.4), (cx - W * s * 0.1, H * s * 0.88),
                (cx - W * s * 0.47, H * s * 0.94)], fill=_shade(cape, 0.75) + (255,))
    im = _fin(big, W, H)
    arm = int(W * 0.19)
    for sx in (-1, 1):
        for k, (dx, dy, sc) in enumerate([(0.30, 0.56, 1.0), (0.40, 0.64, 0.85), (0.22, 0.66, 0.8)]):
            sp = sphere(int(arm * sc), (235, 235, 245) if k != 1 else (170, 170, 180), spec=0.7)
            im.alpha_composite(sp, (int(W * (0.5 + sx * dx) - sp.width / 2), int(H * dy - sp.height / 2)))
    d = int(W * 0.56)
    ball = sphere(d, _c(p.get("color"), (50, 90, 235)))
    big2 = _canvas(d, d)
    dr2 = ImageDraw.Draw(big2)
    r = d * s / 2
    dr2.rounded_rectangle([r * 0.08, r * 0.55, r * 1.92, r * 1.02], radius=r * 0.2, fill=(25, 20, 40, 255))
    for sx in (-1, 1):
        x = r + sx * r * 0.42
        dr2.ellipse([x - r * 0.24, r * 0.66, x + r * 0.24, r * 0.98], fill=(255, 255, 255, 255))
        dr2.ellipse([x - r * 0.11, r * 0.72, x + r * 0.11, r * 0.95], fill=(170, 20, 30, 255))
        dr2.ellipse([x - r * 0.04 + sx * 0.0, r * 0.76, x + r * 0.04, r * 0.84], fill=(255, 255, 255, 255))
    dr2.arc([r * 0.6, r * 1.3, r * 1.4, r * 1.75], 200, 340, fill=(15, 15, 30, 255), width=int(r * 0.07))
    ball.alpha_composite(_fin(big2, d, d))
    im.alpha_composite(ball, (int(W / 2 - d / 2), int(H * 0.02)))
    return im


def a_bacteria_mala(w, p):
    d = int(w)
    col = _c(p.get("color"), (112, 40, 190))
    S = SS
    big = _canvas(d, d)
    dr = ImageDraw.Draw(big)
    c = d * S / 2
    n = 20
    r0 = c * 0.6
    rnd = random.Random(int(p.get("var", 0)) + 3)
    for i in range(n):
        a = 2 * math.pi * i / n + 0.05
        L = c * rnd.uniform(0.95, 1.0)
        hw = 0.17
        dr.polygon([(c + r0 * 0.85 * math.cos(a - hw), c + r0 * 0.85 * math.sin(a - hw)),
                    (c + L * math.cos(a), c + L * math.sin(a)),
                    (c + r0 * 0.85 * math.cos(a + hw), c + r0 * 0.85 * math.sin(a + hw))], fill=_shade(col, 1.08) + (255,), outline=_shade(col, 0.6) + (255,))
    im = _fin(big, d, d)
    bd = int(d * 0.68)
    # cuerpo: esfera con luz suave desde abajo-izquierda (aspecto aterciopelado)
    body = sphere(bd, col, spec=0.15, dark=0.5, light=(-0.35, 0.25))
    big2 = _canvas(bd, bd)
    d2 = ImageDraw.Draw(big2)
    r = bd * S / 2
    # brillo rosado
    d2.ellipse([r * 0.35, r * 0.2, r * 0.85, r * 0.55], fill=(235, 190, 255, 120))
    d2.ellipse([r * 0.5, r * 0.28, r * 0.72, r * 0.42], fill=(255, 240, 255, 200))
    # ojos grandes
    for sx in (-1, 1):
        x = r + sx * r * 0.36
        d2.ellipse([x - r * 0.27, r * 0.7, x + r * 0.27, r * 1.2], fill=(255, 255, 255, 255))
        d2.ellipse([x - r * 0.13 - sx * r * 0.03, r * 0.84, x + r * 0.13 - sx * r * 0.03, r * 1.16], fill=(25, 10, 40, 255))
        d2.ellipse([x - r * 0.06 - sx * r * 0.05, r * 0.88, x + r * 0.02 - sx * r * 0.05, r * 0.97], fill=(255, 255, 255, 255))
        xo, xi = x + sx * r * 0.36, x - sx * r * 0.3   # exterior alto, interior bajo (ceño fruncido)
        d2.polygon([(xo, r * 0.44), (xi, r * 0.7), (xi, r * 0.9 - r * 0.0), (xo, r * 0.66)], fill=(40, 12, 70, 255))
    d2.arc([r * 0.6, r * 1.42, r * 1.4, r * 1.78], 200, 340, fill=(30, 10, 50, 255), width=int(r * 0.07))
    body.alpha_composite(_fin(big2, bd, bd))
    im.alpha_composite(body, (int((d - bd) / 2), int((d - bd) / 2)))
    return _aura(im, _shade(col, 1.6), d * 0.06, 0.45).resize((int(d * 1.24), int(d * 1.24)), Image.LANCZOS)


def a_bacteria_buena(w, p):
    """Bacilo dorado brillante con carita (como cápsula)."""
    W, H = int(w), int(w * 0.44)
    col = _c(p.get("color"), (240, 168, 38))
    im = pill3d(W, H, col, spec=0.35, dark=0.62, light=(-0.2, -0.5))
    S = SS
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    r = H * S / 2
    # borde más oscuro
    dr.rounded_rectangle([1, 1, W * S - 1, H * S - 1], radius=r, outline=_shade(col, 0.62) + (150,), width=max(2, int(H * 0.03 * S)))
    # brillo largo inferior y fino superior
    dr.rounded_rectangle([W * S * 0.16, H * S * 0.66, W * S * 0.84, H * S * 0.78], radius=H * S * 0.06, fill=(255, 250, 225, 215))
    dr.rounded_rectangle([W * S * 0.12, H * S * 0.13, W * S * 0.62, H * S * 0.2], radius=H * S * 0.04, fill=(255, 250, 225, 150))
    # cara
    cx, cy = W * S * 0.5, H * S * 0.47
    for sx in (-1, 1):
        x = cx + sx * H * S * 0.34
        dr.ellipse([x - H * S * 0.06, cy - H * S * 0.1, x + H * S * 0.06, cy + H * S * 0.1], fill=(30, 18, 10, 255))
        dr.ellipse([x - H * S * 0.025, cy - H * S * 0.075, x + H * S * 0.012, cy - H * S * 0.03], fill=(255, 255, 255, 255))
        dr.ellipse([x + sx * H * S * 0.08 - H * S * 0.08, cy + H * S * 0.08, x + sx * H * S * 0.08 + H * S * 0.08, cy + H * S * 0.2], fill=(255, 120, 110, 110))
    dr.arc([cx - H * S * 0.14, cy - H * S * 0.02, cx + H * S * 0.14, cy + H * S * 0.2], 15, 165, fill=(30, 18, 10, 255), width=max(2, int(H * 0.035 * S)))
    im.alpha_composite(_fin(big, W, H))
    return _aura(im, (255, 200, 90), H * 0.1, 0.22)


def a_burbuja(w, p):
    d = int(w)
    big = _canvas(d, d)
    dr = ImageDraw.Draw(big)
    s = SS
    col = _c(p.get("color"), (205, 230, 255))
    dr.ellipse([2, 2, d * s - 2, d * s - 2], fill=col + (38,), outline=col + (210,), width=max(2, int(d * 0.025 * s)))
    dr.arc([d * s * 0.1, d * s * 0.1, d * s * 0.9, d * s * 0.9], 190, 260, fill=(255, 255, 255, 255), width=max(2, int(d * 0.035 * s)))
    dr.arc([d * s * 0.1, d * s * 0.1, d * s * 0.9, d * s * 0.9], 10, 50, fill=(255, 255, 255, 170), width=max(2, int(d * 0.02 * s)))
    dr.ellipse([d * s * 0.22, d * s * 0.16, d * s * 0.42, d * s * 0.28], fill=(255, 255, 255, 200))
    return _fin(big, d, d)


def a_persona(w, p):
    W, H = int(w), int(w * 1.15)
    v = int(p.get("var", 0))
    rnd = random.Random(v * 7919 + 13)
    skins = [(247, 214, 186), (232, 180, 140), (198, 134, 96), (141, 90, 62), (96, 62, 44)]
    hairs = [(40, 28, 22), (90, 56, 30), (220, 176, 70), (170, 60, 40), (25, 25, 30), (150, 150, 160)]
    shirts = [(214, 60, 90), (60, 140, 220), (120, 190, 80), (240, 160, 40), (150, 80, 200), (40, 170, 160)]
    skin = _c(p.get("skin"), rnd.choice(skins))
    hair = _c(p.get("hair"), rnd.choice(hairs))
    shirt = _c(p.get("shirt"), rnd.choice(shirts))
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    s = SS
    cx = W * s / 2
    dr.rounded_rectangle([cx - W * s * 0.46, H * s * 0.58, cx + W * s * 0.46, H * s * 1.2], radius=W * s * 0.25,
                         fill=shirt + (255,))
    dr.rectangle([cx - W * s * 0.09, H * s * 0.5, cx + W * s * 0.09, H * s * 0.64], fill=_shade(skin, 0.9) + (255,))
    long_hair = rnd.random() < 0.5
    if long_hair:
        dr.rounded_rectangle([cx - W * s * 0.34, H * s * 0.1, cx + W * s * 0.34, H * s * 0.62], radius=W * s * 0.2,
                             fill=hair + (255,))
    dr.ellipse([cx - W * s * 0.27, H * s * 0.18, cx + W * s * 0.27, H * s * 0.62], fill=skin + (255,))
    dr.chord([cx - W * s * 0.3, H * s * 0.1, cx + W * s * 0.3, H * s * 0.5], 180, 360, fill=hair + (255,))
    for sx in (-1, 1):
        dr.ellipse([cx + sx * W * s * 0.11 - W * s * 0.03, H * s * 0.38, cx + sx * W * s * 0.11 + W * s * 0.03,
                    H * s * 0.43], fill=(40, 30, 30, 255))
    dr.arc([cx - W * s * 0.1, H * s * 0.4, cx + W * s * 0.1, H * s * 0.54], 20, 160, fill=(120, 40, 40, 255),
           width=max(2, int(W * 0.012 * s)))
    return _fin(big, W, H)


# ---------------------------------------------------------------- objetos
def a_medidor(w, p):
    """Medidor semicircular tipo pH (valor 0-14) con arco arcoíris."""
    W = int(w)
    H = int(w * 0.66)
    val = max(0.0, min(14.0, float(p.get("value", 7))))
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = W / 2, W * 0.56
    dx, dy = x - cx, y - cy
    r = np.sqrt(dx * dx + dy * dy)
    ang = np.degrees(np.arctan2(-dy, dx))  # 0 derecha, 90 arriba, 180 izquierda
    R = W / 2

    def ring(r0, r1):
        e = np.clip(np.minimum(r - r0 * R, r1 * R - r) , 0, 1)
        return e
    top = (dy <= W * 0.02)
    out = np.zeros((H, W, 4), np.float32)
    # marco metálico
    m = np.clip(R - r, 0, 1) * top
    metal = 135 + 100 * np.clip(np.cos(np.radians(ang - 120)), -1, 1) - 60 * np.clip((r / R - 0.9) * 10, 0, 1)
    out[..., :3] = metal[..., None]
    out[..., 3] = m * 255
    # cara oscura
    f = np.clip(R * 0.86 - r, 0, 1) * top
    face = 28 + 22 * (r / R)
    for k in range(3):
        out[..., k] = out[..., k] * (1 - f) + face * f * (1 if k < 2 else 1.4)
    # arco arcoíris
    arc = np.clip(np.minimum(r - R * 0.47, R * 0.74 - r), 0, 1) * top * (ang >= 0) * (ang <= 180)
    hue = np.clip((180 - ang) / 180, 0, 1) * 0.78
    hh = np.zeros((H, W, 3), np.float32)
    for yy in range(0, H):
        pass
    hsv = np.stack([hue, np.ones_like(hue) * 0.95, np.ones_like(hue) * 0.97], -1)
    rgb = _hsv2rgb(hsv)
    for k in range(3):
        out[..., k] = out[..., k] * (1 - arc) + rgb[..., k] * 255 * arc
    out[..., 3] = np.maximum(out[..., 3], arc * 255)
    im = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    s = SS
    a = math.radians(180 - val / 14 * 180)
    L = R * 0.72
    nx, ny = cx * s + L * s * math.cos(a), cy * s - L * s * math.sin(a)
    dr.line([cx * s, cy * s, nx, ny], fill=(235, 235, 240, 255), width=int(W * 0.012 * s))
    dr.ellipse([cx * s - W * 0.035 * s, cy * s - W * 0.035 * s, cx * s + W * 0.035 * s, cy * s + W * 0.035 * s],
               fill=(220, 220, 228, 255), outline=(90, 90, 100, 255), width=int(W * 0.008 * s))
    im.alpha_composite(_fin(big, W, H))
    lab = p.get("label", f"pH {val:g}")
    t1 = text_layer(lab, "bold", int(W * 0.115), fill=(150, 255, 160), stroke=2, stroke_fill=(10, 60, 20), max_w=W)
    im.alpha_composite(t1, (int(cx - t1.width / 2), int(cy - W * 0.2 - t1.height / 2)))
    for txt, px, col in (("ÁCIDO", 0.17, (255, 120, 110)), ("ALCALINO", 0.8, (150, 150, 255))):
        t = text_layer(txt, "bold", int(W * 0.045), fill=col, max_w=W)
        im.alpha_composite(t, (int(W * px - t.width / 2), int(cy + W * 0.02)))
    return im


def _hsv2rgb(hsv):
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    p_, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    r = np.choose(i, [v, q, p_, p_, t, v])
    g = np.choose(i, [t, v, v, q, p_, p_])
    b = np.choose(i, [p_, p_, t, v, v, q])
    return np.stack([r, g, b], -1)


def a_puerta(w, p):
    W, H = int(w), int(w * 1.6)
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    s = SS
    wood = _c(p.get("color"), (140, 86, 50))
    dr.rectangle([0, 0, W * s, H * s], fill=_shade(wood, 0.55) + (255,))
    dr.rectangle([W * s * 0.06, H * s * 0.04, W * s * 0.94, H * s * 1.0], fill=wood + (255,))
    for (a, b, c_, d_) in [(0.16, 0.08, 0.84, 0.46), (0.16, 0.54, 0.84, 0.94)]:
        dr.rectangle([W * s * a, H * s * b, W * s * c_, H * s * d_], fill=_shade(wood, 0.82) + (255,),
                     outline=_shade(wood, 0.6) + (255,), width=int(W * 0.012 * s))
    dr.ellipse([W * s * 0.77, H * s * 0.5, W * s * 0.86, H * s * 0.5 + W * s * 0.09], fill=(235, 190, 80, 255))
    return _fin(big, W, H)


def a_cartel(w, p):
    """Cartel colgante rojo con texto (p. ej. «NO MOLESTAR»)."""
    W, H = int(w), int(w * 0.78)
    txt = p.get("text", "NO MOLESTAR")
    col = _c(p.get("color"), (214, 40, 60))
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    s = SS
    dr.rounded_rectangle([W * s * 0.03, H * s * 0.2, W * s * 0.97, H * s * 0.98], radius=W * s * 0.07,
                         fill=col + (255,), outline=(255, 235, 235, 255), width=int(W * 0.018 * s))
    dr.ellipse([W * s * 0.44, H * s * 0.02, W * s * 0.56, H * s * 0.2], outline=(230, 190, 90, 255),
               width=int(W * 0.02 * s))
    im = _fin(big, W, H)
    t = text_layer(txt, "display", int(W * 0.19), fill=(255, 255, 255), stroke=0, max_w=int(W * 0.8), upper=True)
    im.alpha_composite(t, (int((W - t.width) / 2), int(H * 0.62 - t.height / 2)))
    return im


def a_etiqueta(w, p):
    """Caja de texto llamativa (cifras, datos): «28 años», «300 km»…"""
    txt = str(p.get("text", "Texto"))
    col = _c(p.get("color"), (214, 30, 40))
    fg = _c(p.get("fg"), (255, 255, 255))
    size = int(w * 0.28) if len(txt) < 12 else int(w * 0.2)
    t = text_layer(txt, "display", size, fill=fg, max_w=int(w * 0.95), upper=bool(p.get("upper", True)))
    padx, pady = int(size * 0.35), int(size * 0.18)
    W, H = t.width + padx * 2, t.height + pady * 2
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    s = SS
    dr.rounded_rectangle([0, 0, W * s, H * s], radius=int(size * 0.16 * s), fill=col + (255,),
                         outline=(255, 255, 255, 230), width=int(size * 0.05 * s))
    im = _fin(big, W, H)
    im.alpha_composite(t, (padx, pady))
    return im


def a_texto(w, p):
    txt = str(p.get("text", "Texto"))
    return text_layer(txt, p.get("font", "display"), int(p.get("size", w * 0.2)), fill=_c(p.get("color"), (255, 255, 255)),
                      stroke=int(p.get("stroke", 6)), max_w=int(w), upper=bool(p.get("upper", True)), shadow=4)


def a_banda(w, p):
    """Cartel ancho tipo rótulo de local («PESCADERÍA»)."""
    txt = p.get("text", "PESCADERÍA")
    W, H = int(w), int(w * 0.3)
    col = _c(p.get("color"), (24, 62, 120))
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    s = SS
    dr.rectangle([0, 0, W * s, H * s], fill=col + (255,))
    dr.rectangle([0, 0, W * s, H * s * 0.05], fill=_shade(col, 1.6) + (255,))
    for i in range(3):
        pts = [(x, H * s * (0.9 + 0.03 * math.sin(x / (W * s) * 20 + i))) for x in range(0, int(W * s), 12)]
        dr.line(pts, fill=(120, 170, 230, 200), width=int(H * 0.012 * s))
    im = _fin(big, W, H)
    t = text_layer(txt, "display", int(H * 0.55), fill=(236, 200, 120), stroke=2, stroke_fill=(70, 50, 10),
                   max_w=int(W * 0.92), upper=True)
    im.alpha_composite(t, (int((W - t.width) / 2), int((H - t.height) / 2)))
    return im


def a_pastilla(w, p):
    W, H = int(w), int(w * 0.42)
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    s = SS
    dr.rounded_rectangle([0, 0, W * s, H * s], radius=H * s / 2, fill=(245, 245, 250, 255))
    dr.rounded_rectangle([W * s * 0.5, 0, W * s, H * s], radius=H * s / 2, fill=(214, 36, 50, 255))
    dr.rectangle([W * s * 0.5, 0, W * s * 0.72, H * s], fill=(214, 36, 50, 255))
    dr.rectangle([W * s * 0.5 - 4, 0, W * s * 0.5 + 4, H * s], fill=(190, 190, 200, 255))
    dr.rounded_rectangle([W * s * 0.06, H * s * 0.1, W * s * 0.94, H * s * 0.3], radius=H * s * 0.1,
                         fill=(255, 255, 255, 140))
    return _fin(big, W, H)


def a_pez(w, p):
    W, H = int(w), int(w * 0.56)
    body = _c(p.get("color"), (150, 170, 185))
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    s = SS
    dr.polygon([(W * s * 0.8, H * s * 0.5), (W * s, H * s * 0.08), (W * s, H * s * 0.92)], fill=_shade(body, 0.7) + (255,))
    dr.polygon([(W * s * 0.3, H * s * 0.25), (W * s * 0.5, H * s * 0.0), (W * s * 0.62, H * s * 0.3)],
               fill=_shade(body, 0.65) + (255,))
    dr.ellipse([0, H * s * 0.2, W * s * 0.86, H * s * 0.8], fill=_shade(body, 0.55) + (255,))
    dr.chord([0, H * s * 0.2, W * s * 0.86, H * s * 0.8], 0, 180, fill=_shade(body, 1.12) + (255,))
    dr.chord([W * s * 0.02, H * s * 0.2, W * s * 0.86, H * s * 0.62], 180, 360, fill=_shade(body, 0.5) + (255,))
    dr.ellipse([W * s * 0.1, H * s * 0.3, W * s * 0.8, H * s * 0.66], fill=body + (255,))
    for i in range(5):
        x = W * s * (0.2 + i * 0.11)
        dr.arc([x, H * s * 0.34, x + W * s * 0.1, H * s * 0.52], 270, 90, fill=_shade(body, 0.8) + (255,), width=3)
    dr.arc([W * s * 0.22, H * s * 0.3, W * s * 0.34, H * s * 0.7], 270, 90, fill=_shade(body, 0.6) + (255,), width=5)
    dr.ellipse([W * s * 0.07, H * s * 0.36, W * s * 0.13, H * s * 0.45], fill=(250, 250, 250, 255), outline=(20, 20, 20, 255), width=3)
    dr.ellipse([W * s * 0.085, H * s * 0.385, W * s * 0.115, H * s * 0.43], fill=(10, 10, 10, 255))
    return _fin(big, W, H)


def a_gato(w, p):
    W, H = int(w), int(w * 1.15)
    fur = _c(p.get("color"), (236, 140, 48))
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    s = SS
    cx = W * s / 2
    dr.arc([cx + W * s * 0.1, H * s * 0.55, cx + W * s * 0.75, H * s * 0.98], 300, 120, fill=fur + (255,), width=int(W * 0.09 * s))
    dr.ellipse([cx - W * s * 0.34, H * s * 0.5, cx + W * s * 0.34, H * s * 0.99], fill=fur + (255,))
    dr.ellipse([cx - W * s * 0.2, H * s * 0.65, cx + W * s * 0.2, H * s * 1.0], fill=(255, 236, 210, 255))
    for sx in (-1, 1):
        dr.polygon([(cx + sx * W * s * 0.12, H * s * 0.04), (cx + sx * W * s * 0.42, H * s * 0.2), (cx + sx * W * s * 0.4, H * s * 0.48)], fill=fur + (255,))
        dr.polygon([(cx + sx * W * s * 0.17, H * s * 0.12), (cx + sx * W * s * 0.34, H * s * 0.22), (cx + sx * W * s * 0.33, H * s * 0.38)], fill=(255, 170, 170, 255))
    dr.ellipse([cx - W * s * 0.4, H * s * 0.12, cx + W * s * 0.4, H * s * 0.68], fill=fur + (255,))
    for k in range(3):
        x = cx + (k - 1) * W * s * 0.09
        dr.polygon([(x - 8, H * s * 0.12), (x + 8, H * s * 0.12), (x, H * s * 0.26)], fill=_shade(fur, 0.7) + (255,))
    dr.ellipse([cx - W * s * 0.18, H * s * 0.44, cx + W * s * 0.18, H * s * 0.64], fill=(255, 236, 210, 255))
    for sx in (-1, 1):
        x = cx + sx * W * s * 0.17
        dr.ellipse([x - W * s * 0.09, H * s * 0.27, x + W * s * 0.09, H * s * 0.46], fill=(255, 255, 255, 255), outline=(60, 40, 20, 255), width=4)
        dr.ellipse([x - W * s * 0.065, H * s * 0.29, x + W * s * 0.065, H * s * 0.45], fill=(70, 170, 70, 255))
        dr.ellipse([x - W * s * 0.03, H * s * 0.31, x + W * s * 0.03, H * s * 0.43], fill=(10, 10, 10, 255))
        dr.ellipse([x - W * s * 0.04, H * s * 0.32, x - W * s * 0.01, H * s * 0.36], fill=(255, 255, 255, 255))
        for k in (-1, 0, 1):
            dr.line([cx + sx * W * s * 0.1, H * s * 0.52 + k * 8, cx + sx * W * s * 0.5, H * s * 0.5 + k * 24], fill=(255, 255, 255, 230), width=4)
    dr.polygon([(cx - 12, H * s * 0.455), (cx + 12, H * s * 0.455), (cx, H * s * 0.485)], fill=(240, 120, 130, 255))
    dr.arc([cx - 20, H * s * 0.48, cx, H * s * 0.52], 0, 180, fill=(120, 60, 40, 255), width=3)
    dr.arc([cx, H * s * 0.48, cx + 20, H * s * 0.52], 0, 180, fill=(120, 60, 40, 255), width=3)
    return _fin(big, W, H)


def a_hielo(w, p):
    """Cama de cubos de hielo (borde inferior)."""
    W, H = int(w), int(w * 0.22)
    rnd = random.Random(5)
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    s = SS
    dr.rectangle([0, H * s * 0.3, W * s, H * s], fill=(190, 225, 245, 255))
    x = -20
    while x < W * s:
        sz = rnd.randint(int(H * s * 0.25), int(H * s * 0.45))
        y = H * s * rnd.uniform(0.0, 0.5)
        dr.rounded_rectangle([x, y, x + sz, y + sz], radius=sz * 0.18, fill=(210, 238, 252, 235), outline=(255, 255, 255, 200), width=3)
        x += sz * rnd.uniform(0.6, 0.9)
    return _fin(big, W, H)


def a_nube_olor(w, p):
    """Ondas de olor verdes que suben."""
    W, H = int(w), int(w * 1.3)
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    s = SS
    col = _c(p.get("color"), (150, 220, 70))
    for k, x0 in enumerate((0.2, 0.5, 0.8)):
        pts = [(W * s * (x0 + 0.08 * math.sin(i / 8 * math.pi * 2)), H * s * (1 - i / 40)) for i in range(41)]
        dr.line(pts, fill=col + (230,), width=int(W * 0.035 * s), joint="curve")
    return _fin(big, W, H)


def a_corazon(w, p):
    d = int(w)
    big = _canvas(d, d)
    dr = ImageDraw.Draw(big)
    s = SS
    col = _c(p.get("color"), (255, 110, 160))
    r = d * s * 0.27
    dr.ellipse([d * s * 0.08, d * s * 0.12, d * s * 0.08 + 2 * r, d * s * 0.12 + 2 * r], fill=col + (255,))
    dr.ellipse([d * s * 0.92 - 2 * r, d * s * 0.12, d * s * 0.92, d * s * 0.12 + 2 * r], fill=col + (255,))
    dr.polygon([(d * s * 0.09, d * s * 0.42), (d * s * 0.91, d * s * 0.42), (d * s * 0.5, d * s * 0.92)], fill=col + (255,))
    return _fin(big, d, d)


def a_estrella(w, p):
    d = int(w)
    big = _canvas(d, d)
    dr = ImageDraw.Draw(big)
    c = d * SS / 2
    pts = []
    for i in range(10):
        r = c * (0.95 if i % 2 == 0 else 0.42)
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((c + r * math.cos(a), c + r * math.sin(a)))
    dr.polygon(pts, fill=_c(p.get("color"), (255, 214, 60)) + (255,), outline=(255, 255, 255, 255))
    return _fin(big, d, d)


def a_flecha(w, p):
    W, H = int(w), int(w * 0.5)
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    s = SS
    col = _c(p.get("color"), (255, 255, 255))
    dr.rectangle([0, H * s * 0.34, W * s * 0.62, H * s * 0.66], fill=col + (255,))
    dr.polygon([(W * s * 0.56, 0), (W * s, H * s * 0.5), (W * s * 0.56, H * s)], fill=col + (255,))
    return _fin(big, W, H)


def a_marca(w, p):
    """Check verde (ok) o cruz roja (no)."""
    d = int(w)
    big = _canvas(d, d)
    dr = ImageDraw.Draw(big)
    s = SS
    ok = p.get("kind", "ok") == "ok"
    col = (60, 200, 110) if ok else (230, 60, 70)
    dr.ellipse([0, 0, d * s, d * s], fill=col + (255,))
    wd = int(d * 0.11 * s)
    if ok:
        dr.line([d * s * 0.26, d * s * 0.52, d * s * 0.43, d * s * 0.7, d * s * 0.76, d * s * 0.32], fill=(255, 255, 255, 255), width=wd, joint="curve")
    else:
        dr.line([d * s * 0.3, d * s * 0.3, d * s * 0.7, d * s * 0.7], fill=(255, 255, 255, 255), width=wd)
        dr.line([d * s * 0.7, d * s * 0.3, d * s * 0.3, d * s * 0.7], fill=(255, 255, 255, 255), width=wd)
    return _fin(big, d, d)


def a_nariz(w, p):
    W, H = int(w), int(w * 1.3)
    skin = _c(p.get("color"), (226, 160, 120))
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    s = SS
    cx = W * s / 2
    dr.polygon([(cx - W * s * 0.12, 0), (cx + W * s * 0.12, 0), (cx + W * s * 0.22, H * s * 0.62), (cx - W * s * 0.22, H * s * 0.62)], fill=_shade(skin, 0.95) + (255,))
    dr.ellipse([cx - W * s * 0.32, H * s * 0.45, cx + W * s * 0.32, H * s * 0.92], fill=skin + (255,))
    for sx in (-1, 1):
        dr.ellipse([cx + sx * W * s * 0.31 - W * s * 0.15, H * s * 0.55, cx + sx * W * s * 0.31 + W * s * 0.15, H * s * 0.9], fill=_shade(skin, 1.05) + (255,))
        dr.ellipse([cx + sx * W * s * 0.14 - W * s * 0.07, H * s * 0.74, cx + sx * W * s * 0.14 + W * s * 0.07, H * s * 0.86], fill=(70, 30, 25, 255))
    dr.ellipse([cx - W * s * 0.1, H * s * 0.52, cx + W * s * 0.06, H * s * 0.62], fill=(255, 230, 205, 160))
    return _fin(big, W, H)


def a_pin(w, p):
    """Marcador de mapa (gota roja)."""
    W, H = int(w), int(w * 1.4)
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    s = SS
    col = _c(p.get("color"), (230, 40, 50))
    dr.polygon([(W * s * 0.12, H * s * 0.38), (W * s * 0.88, H * s * 0.38), (W * s * 0.5, H * s * 1.0)], fill=col + (255,))
    dr.ellipse([0, 0, W * s, W * s * 0.98], fill=col + (255,))
    dr.ellipse([W * s * 0.3, W * s * 0.3, W * s * 0.7, W * s * 0.7], fill=(255, 255, 255, 255))
    return _fin(big, W, H)


def a_calendario(w, p):
    d = int(w)
    big = _canvas(d, d)
    dr = ImageDraw.Draw(big)
    s = SS
    dr.rounded_rectangle([d * s * 0.04, d * s * 0.1, d * s * 0.96, d * s * 0.96], radius=d * s * 0.1, fill=(244, 244, 238, 255), outline=(40, 40, 40, 255), width=int(d * 0.025 * s))
    dr.rounded_rectangle([d * s * 0.04, d * s * 0.1, d * s * 0.96, d * s * 0.36], radius=d * s * 0.1, fill=(214, 36, 50, 255))
    dr.rectangle([d * s * 0.04, d * s * 0.26, d * s * 0.96, d * s * 0.36], fill=(214, 36, 50, 255))
    for x in (0.28, 0.5, 0.72):
        dr.ellipse([d * s * (x - 0.04), d * s * 0.03, d * s * (x + 0.04), d * s * 0.17], fill=(60, 60, 60, 255))
    im = _fin(big, d, d)
    t1 = text_layer(p.get("month", ""), "bold", int(d * 0.16), fill=(255, 255, 255), max_w=d)
    im.alpha_composite(t1, (int((d - t1.width) / 2), int(d * 0.2)))
    t2 = text_layer(str(p.get("day", "")), "display", int(d * 0.46), fill=(30, 30, 30), max_w=d)
    im.alpha_composite(t2, (int((d - t2.width) / 2), int(d * 0.4)))
    return im


def a_emoji(w, p):
    """Emoji a color del sistema (Segoe UI Emoji en Windows / Noto Color Emoji)."""
    from PIL import ImageFont
    ch = str(p.get("char", "😀"))
    for path, size in (("seguiemj.ttf", 109), ("C:/Windows/Fonts/seguiemj.ttf", 109),
                       ("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", 109), ("NotoColorEmoji.ttf", 109)):
        try:
            f = ImageFont.truetype(path, size)
            im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((10, 10), ch, font=f, embedded_color=True)
            bb = im.getbbox()
            if bb:
                im = im.crop(bb)
                return im.resize((int(w), max(1, int(w * im.height / im.width))), Image.LANCZOS)
        except Exception:
            continue
    return a_texto(w, {"text": ch, "size": w * 0.6})


def a_jabon(w, p):
    W, H = int(w), int(w * 0.58)
    col = _c(p.get("color"), (255, 120, 170))
    im = pill3d(W, H, col, spec=0.6, dark=0.62)
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    dr.rounded_rectangle([W * SS * 0.08, H * SS * 0.1, W * SS * 0.7, H * SS * 0.3], radius=H * SS * 0.1, fill=(255, 255, 255, 120))
    im.alpha_composite(_fin(big, W, H))
    return im


def a_regadera(w, p):
    W, H = int(w), int(w * 0.8)
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    s = SS
    dr.line([W * s * 0.1, 0, W * s * 0.1, H * s * 0.35, W * s * 0.4, H * s * 0.35], fill=(150, 154, 162, 255), width=int(W * 0.05 * s), joint="curve")
    dr.polygon([(W * s * 0.3, H * s * 0.3), (W * s * 0.95, H * s * 0.55), (W * s * 0.6, H * s * 0.95), (W * s * 0.18, H * s * 0.5)], fill=(176, 180, 190, 255), outline=(110, 114, 124, 255))
    for i in range(6):
        dr.ellipse([W * s * (0.4 + 0.07 * i), H * s * (0.55 + 0.045 * i) - 6, W * s * (0.4 + 0.07 * i) + 12, H * s * (0.55 + 0.045 * i) + 6], fill=(80, 84, 94, 255))
    return _fin(big, W, H)


def a_agua(w, p):
    """Chorros de agua (usar con anim fall)."""
    W, H = int(w), int(w * 1.6)
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    s = SS
    rnd = random.Random(4)
    for i in range(26):
        x = rnd.uniform(0.05, 0.95) * W * s
        y = rnd.uniform(0, 0.8) * H * s
        l = rnd.uniform(0.08, 0.25) * H * s
        dr.line([x, y, x - W * s * 0.03, y + l], fill=(220, 255, 235, rnd.randint(120, 230)), width=max(2, int(W * 0.008 * s)))
    return _fin(big, W, H)


# ---------------------------------------------------------------- registro
# nombre: (función, alto/ancho aproximado, descripción, parámetros)
ASSETS = {
    "esfera": (a_esfera, 1.0, "Bola con carita (personaje base)", "color, mood: neutral|happy|angry|sad|scared|none"),
    "villano": (a_villano, 1.0, "Bolita azul enmascarada con capa y brazos", "color, cape"),
    "bacteria_mala": (a_bacteria_mala, 1.0, "Bacteria morada con picos y cara de enojo", "color, mood"),
    "bacteria_buena": (a_bacteria_buena, 0.38, "Bacilo amarillo sonriente", "color"),
    "burbuja": (a_burbuja, 1.0, "Burbuja translúcida", "color"),
    "persona": (a_persona, 1.15, "Persona de busto (cada copia con var distinto cambia piel, pelo y ropa)", "skin, hair, shirt, var"),
    "medidor": (a_medidor, 0.66, "Medidor semicircular tipo pH", "value (0-14), label"),
    "puerta": (a_puerta, 1.6, "Puerta de madera", "color"),
    "cartel": (a_cartel, 0.78, "Cartel colgante rojo con texto", "text, color"),
    "etiqueta": (a_etiqueta, 0.4, "Caja roja con texto grande para datos (28 años, 300 km)", "text, color, fg"),
    "texto": (a_texto, 0.3, "Texto con contorno", "text, color, size, stroke"),
    "banda": (a_banda, 0.3, "Rótulo ancho de local", "text, color"),
    "pastilla": (a_pastilla, 0.42, "Pastilla roja y blanca", ""),
    "pez": (a_pez, 0.5, "Pescado plateado", "color"),
    "gato": (a_gato, 1.15, "Gato naranja sentado", "color"),
    "hielo": (a_hielo, 0.22, "Cama de hielo (poner al borde inferior)", ""),
    "olor": (a_nube_olor, 1.3, "Ondas verdes de olor", "color"),
    "corazon": (a_corazon, 1.0, "Corazón", "color"),
    "estrella": (a_estrella, 1.0, "Estrella", "color"),
    "flecha": (a_flecha, 0.5, "Flecha apuntando a la derecha (usa rot)", "color"),
    "marca": (a_marca, 1.0, "Check verde o cruz roja", "kind: ok|no"),
    "nariz": (a_nariz, 1.3, "Nariz", "color"),
    "pin": (a_pin, 1.4, "Marcador de mapa", "color"),
    "calendario": (a_calendario, 1.0, "Hoja de calendario", "month, day"),
    "jabon": (a_jabon, 0.58, "Jabón rosa brillante", "color"),
    "regadera": (a_regadera, 0.8, "Cabezal de regadera", ""),
    "agua": (a_agua, 1.6, "Chorros de agua (anim fall)", ""),
    "emoji": (a_emoji, 1.0, "Emoji a color", "char"),
}

_cache: dict = {}


def sprite(name: str, width: int, params: dict) -> Image.Image:
    key = (name, int(width), tuple(sorted((k, str(v)) for k, v in params.items())))
    hit = _cache.get(key)
    if hit is None:
        if name not in ASSETS:
            raise KeyError(f"Elemento desconocido: «{name}». Disponibles: {', '.join(ASSETS)}")
        hit = ASSETS[name][0](max(8, int(width)), params)
        if len(_cache) > 400:
            _cache.clear()
        _cache[key] = hit
    return hit
