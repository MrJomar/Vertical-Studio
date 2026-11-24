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
    dr.ellipse([d * s * 0.22, d * s * 0.16, d * s * 0.42, d * s * 0.28], fill=(255, 255, 255, 110))
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
def a_molecula(w, p):
    """Molécula de bolas y palitos (trimetilamina): N azul con cara enojada, 3 carbonos grises, 9 hidrógenos."""
    from PIL import ImageFilter
    W, H = int(w), int(w * 0.92)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    N = (0.5, 0.3)
    Cs = [(0.25, 0.62), (0.75, 0.62), (0.5, 0.76)]
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    s = SS
    rn = W * 0.17
    rc = W * 0.115
    rh = W * 0.075
    Hs = []
    for cx, cy in Cs:
        dr.line([(N[0] * W * s, N[1] * H * s), (cx * W * s, cy * H * s)], fill=(190, 190, 200, 255), width=int(W * 0.028 * s))
        for k, ang in enumerate((-2.5, -0.65, 1.55)):
            hx, hy = cx * W + math.cos(ang) * W * 0.125, cy * H + math.sin(ang) * W * 0.125
            dr.line([(cx * W * s, cy * H * s), (hx * s, hy * s)], fill=(190, 190, 200, 255), width=int(W * 0.02 * s))
            Hs.append((hx, hy))
    im.alpha_composite(_fin(big, W, H))
    for hx, hy in sorted(Hs, key=lambda q: q[1]):
        sp = sphere(int(rh * 2), (240, 240, 248), spec=0.8)
        im.alpha_composite(sp, (int(hx - rh), int(hy - rh)))
    for cx, cy in Cs:
        sp = sphere(int(rc * 2), (95, 98, 108), spec=0.7)
        im.alpha_composite(sp, (int(cx * W - rc), int(cy * H - rc)))
    nb = sphere(int(rn * 2), _c(p.get("color"), (45, 85, 235)))
    d = nb.width
    fb = _canvas(d, d)
    _face(ImageDraw.Draw(fb), d * s / 2, d * s / 2, d * s / 2, p.get("mood", "angry"))
    nb.alpha_composite(_fin(fb, d, d))
    im.alpha_composite(nb, (int(N[0] * W - rn), int(N[1] * H - rn)))
    return im


def a_burbuja_villano(w, p):
    d = int(w)
    im = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    v = a_villano(int(d * 0.66), {})
    im.alpha_composite(v, ((d - v.width) // 2, int(d * 0.2)))
    im.alpha_composite(a_burbuja(d, p))
    return im


def a_luz(w, p):
    """Resplandor suave (luz bajo una puerta, foco, aura). Usa color y h (relación alto/ancho)."""
    W = int(w)
    H = max(4, int(w * float(p.get("h", 0.35))))
    col = np.array(_c(p.get("color"), (255, 120, 170)), np.float32)
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    r2 = ((x - W / 2) / (W / 2)) ** 2 + ((y - H / 2) / (H / 2)) ** 2
    a = np.exp(-r2 * 3.2) * np.clip(1.15 - np.sqrt(r2), 0, 1) * 235
    out = np.dstack([np.broadcast_to(col, (H, W, 3)), a]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def a_humo(w, p):
    """Nubes de humo o niebla translúcida (color: verde para olores, gris para vapor)."""
    from PIL import ImageFilter
    W, H = int(w), int(w * 0.6)
    col = _c(p.get("color"), (140, 230, 90))
    m = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(m)
    rnd = random.Random(7)
    for _ in range(9):
        cx, cy, r = rnd.uniform(0.2, 0.8) * W, rnd.uniform(0.3, 0.7) * H, rnd.uniform(0.14, 0.27) * W
        dr.ellipse([cx - r, cy - r * 0.8, cx + r, cy + r * 0.8], fill=rnd.randint(90, 170))
    m = m.filter(ImageFilter.GaussianBlur(W * 0.07))
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    fade = np.clip(1.2 - np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2), 0, 1)
    m = Image.fromarray((np.asarray(m, np.float32) * fade).astype(np.uint8), "L")
    im = Image.new("RGBA", (W, H), col + (0,))
    im.putalpha(m)
    return im


# ----------------------------------------------------------------------------- cuerpo humano / ciencia
def _glass(dr, pts_list, width, rim=(170, 225, 255), fill=(70, 130, 210), alpha=120):
    """Dibuja un tubo translúcido tipo cristal siguiendo una o varias polilíneas (borde claro + relleno azul)."""
    for pts in pts_list:
        dr.line(pts, fill=rim + (235,), width=int(width), joint="curve")
        for p_ in (pts[0], pts[-1]):
            dr.ellipse([p_[0] - width / 2, p_[1] - width / 2, p_[0] + width / 2, p_[1] + width / 2], fill=rim + (235,))
    for pts in pts_list:
        dr.line(pts, fill=fill + (alpha,), width=int(width * 0.86), joint="curve")
        for p_ in (pts[0], pts[-1]):
            r_ = width * 0.43
            dr.ellipse([p_[0] - r_, p_[1] - r_, p_[0] + r_, p_[1] + r_], fill=fill + (alpha,))


def _sm(pts, n=12):
    """Suaviza una polilínea (Catmull-Rom)."""
    out = []
    P = [pts[0]] + list(pts) + [pts[-1]]
    for i in range(1, len(P) - 2):
        for k in range(n):
            t = k / n
            out.append(tuple(0.5 * ((2 * P[i][j]) + (-P[i - 1][j] + P[i + 1][j]) * t +
                                    (2 * P[i - 1][j] - 5 * P[i][j] + 4 * P[i + 1][j] - P[i + 2][j]) * t * t +
                                    (-P[i - 1][j] + 3 * P[i][j] - 3 * P[i + 1][j] + P[i + 2][j]) * t ** 3) for j in (0, 1)))
    out.append(tuple(pts[-1]))
    return out


def a_gota(w, p):
    W, H = int(w), int(w * 1.3)
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    S = SS
    col = _c(p.get("color"), (214, 40, 57))
    r = W * S * 0.42
    cx, cy = W * S / 2, H * S * 0.66
    dr.polygon([(cx, H * S * 0.04), (cx - r * 0.92, cy - r * 0.35), (cx + r * 0.92, cy - r * 0.35)], fill=_shade(col, 0.8) + (255,))
    dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_shade(col, 0.8) + (255,))
    r2 = r * 0.82
    dr.ellipse([cx - r2 * 0.95, cy - r2 * 0.9, cx + r2 * 0.75, cy + r2 * 0.75], fill=col + (255,))
    dr.ellipse([cx - r * 0.55, cy - r * 0.55, cx - r * 0.2, cy - r * 0.05], fill=_shade(col, 1.0 + 0.0) and (250, 170, 175, 255))
    return _fin(big, W, H)


def a_globulo(w, p):
    d = int(w)
    col = _c(p.get("color"), (220, 40, 60))
    base = sphere(d, col, spec=0.35, dark=0.5)
    H = int(d * 0.82)
    base = base.resize((d, H), Image.LANCZOS)
    big = Image.new("RGBA", (d * SS, H * SS), (0, 0, 0, 0))
    dr = ImageDraw.Draw(big)
    dr.ellipse([d * SS * 0.27, H * SS * 0.3, d * SS * 0.73, H * SS * 0.7], fill=_shade(col, 0.55) + (190,))
    dim = _fin(big, d, H)
    from PIL import ImageFilter
    dim = dim.filter(ImageFilter.GaussianBlur(max(1, d * 0.03)))
    base.alpha_composite(dim)
    return base


def a_rayo(w, p):
    W, H = int(w), int(w * 1.6)
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    S = SS
    pts = [(.62, .0), (.12, .56), (.44, .56), (.30, 1.0), (.88, .38), (.55, .38)]
    pts = [(x * W * S, y * H * S) for x, y in pts]
    col = _c(p.get("color"), (255, 214, 60))
    dr.polygon(pts, fill=col + (255,), outline=_shade(col, 0.6) + (255,))
    dr.line(pts + [pts[0]], fill=_shade(col, 0.55) + (255,), width=int(W * S * 0.03))
    dr.polygon([(.58 * W * S, .08 * H * S), (.26 * W * S, .5 * H * S), (.4 * W * S, .5 * H * S)], fill=(255, 243, 150, 255))
    return _fin(big, W, H)


def a_hueso(w, p):
    W, H = int(w), int(w * 0.34)
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    S = SS
    col = _c(p.get("color"), (242, 232, 206))
    sh = _shade(col, 0.78)
    dr.rounded_rectangle([W * S * 0.12, H * S * 0.3, W * S * 0.88, H * S * 0.7], radius=H * S * 0.2, fill=col + (255,), outline=sh + (255,), width=int(S * 2))
    r = H * S * 0.26
    for cx, sgn in ((W * S * 0.1, 1), (W * S * 0.9, -1)):
        for cy in (H * S * 0.3, H * S * 0.7):
            dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (255,), outline=sh + (255,), width=int(S * 2))
    dr.rectangle([W * S * 0.14, H * S * 0.34, W * S * 0.86, H * S * 0.42], fill=(255, 250, 236, 255))
    return _fin(big, W, H)


def a_reloj(w, p):
    d = int(w)
    big = _canvas(d, d)
    dr = ImageDraw.Draw(big)
    S = SS
    c = d * S / 2
    dr.ellipse([c * 0.04, c * 0.1, c * 1.96, c * 2.0], fill=(0, 0, 0, 70))
    dr.ellipse([0, 0, 2 * c * 0.97, 2 * c * 0.97], fill=(70, 78, 96, 255))
    dr.ellipse([c * 0.1, c * 0.1, c * 1.87, c * 1.87], fill=(250, 250, 248, 255))
    for i in range(12):
        a = i * math.pi / 6
        r0, r1 = c * (0.72 if i % 3 else 0.64), c * 0.82
        dr.line([(c * .97 + r0 * math.sin(a), c * .97 - r0 * math.cos(a)), (c * .97 + r1 * math.sin(a), c * .97 - r1 * math.cos(a))],
                fill=(60, 66, 80, 255), width=int(S * (2 if i % 3 else 4)))
    hh, mm = float(p.get("hour", 10)), float(p.get("min", 10))
    for ang, ln, wd in (((hh % 12 + mm / 60) * math.pi / 6, 0.45, 7), (mm * math.pi / 30, 0.68, 5)):
        dr.line([(c * .97, c * .97), (c * .97 + c * ln * math.sin(ang), c * .97 - c * ln * math.cos(ang))], fill=(30, 34, 46, 255), width=int(S * wd))
    dr.ellipse([c * .97 - S * 6, c * .97 - S * 6, c * .97 + S * 6, c * .97 + S * 6], fill=(214, 40, 57, 255))
    return _fin(big, d, d)


def a_cerebro(w, p):
    W, H = int(w), int(w * 0.85)
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    S = SS
    col = _c(p.get("color"), (236, 150, 170))
    dk = _shade(col, 0.62)
    # tronco y cerebelo
    dr.rounded_rectangle([W * S * 0.46, H * S * 0.66, W * S * 0.58, H * S * 1.0], radius=W * S * 0.04, fill=_shade(col, 0.9) + (255,))
    dr.ellipse([W * S * 0.56, H * S * 0.62, W * S * 0.9, H * S * 0.88], fill=_shade(col, 0.85) + (255,), outline=dk + (255,), width=int(S * 2))
    # hemisferio
    for off, sc in ((0, 1.0),):
        dr.ellipse([W * S * 0.04, H * S * 0.02, W * S * 0.96, H * S * 0.78], fill=dk + (255,))
        dr.ellipse([W * S * 0.07, H * S * 0.04, W * S * 0.93, H * S * 0.74], fill=col + (255,))
    rnd = random.Random(int(p.get("seed", 5)))
    for _ in range(26):                                  # circunvoluciones
        x0, y0 = rnd.uniform(.14, .82), rnd.uniform(.1, .62)
        pts, a = [], rnd.uniform(0, 6.28)
        x, y = x0, y0
        for _k in range(7):
            pts.append((x * W * S, y * H * S))
            a += rnd.uniform(-1.1, 1.1)
            x += 0.045 * math.cos(a)
            y += 0.045 * math.sin(a)
            x, y = min(.9, max(.1, x)), min(.7, max(.08, y))
        dr.line(_sm(pts, 5), fill=dk + (255,), width=int(S * 4), joint="curve")
    dr.arc([W * S * 0.2, H * S * 0.55, W * S * 0.8, H * S * 0.9], 200, 340, fill=dk + (230,), width=int(S * 3))
    dr.ellipse([W * S * 0.2, H * S * 0.08, W * S * 0.46, H * S * 0.22], fill=(246, 178, 194, 255))
    return _fin(big, W, H)


def a_nervio(w, p):
    """Cable nervioso amarillo con vainas; pinch (0-1) lo aprieta en ese punto; glow lo enciende."""
    W, H = int(w), int(w * 1.6)
    pad = int(W * 0.3)
    big = _canvas(W + 2 * pad, H)
    dr = ImageDraw.Draw(big)
    S = SS
    col = _c(p.get("color"), (255, 214, 63))
    pinch = p.get("pinch")
    pinch = None if pinch in (None, "", False) else float(pinch)
    N = 220
    path = [((pad + W * (0.5 + 0.16 * math.sin(i / N * 6.28 * 1.1))) * S, (0.03 + 0.94 * i / N) * H * S) for i in range(N + 1)]
    base_r = W * S * 0.085

    def radius(i):
        t = i / N
        return base_r * (1 - 0.68 * math.exp(-((t - pinch) / 0.05) ** 2)) if pinch is not None else base_r

    for layer in (0, 1):
        for i, (x, y) in enumerate(path):
            r = radius(i) + (S * 2 if layer == 0 else 0)
            tint = _shade(col, 0.55) if layer == 0 else col
            if layer and pinch is not None:
                f = math.exp(-((i / N - pinch) / 0.05) ** 2)
                tint = tuple(int(col[k] * (1 - 0.75 * f) + (232, 64, 64)[k] * 0.75 * f) for k in range(3))
            dr.ellipse([x - r, y - r, x + r, y + r], fill=tint + (255,))
    for i in range(10, N, 18):                            # vainas de mielina
        x, y = path[i]
        r = radius(i)
        dr.line([(x - r, y), (x + r, y)], fill=_shade(col, 0.7) + (255,), width=int(S * 3))
    for i in range(N):                                    # brillo
        x, y = path[i]
        r = radius(i)
        dr.ellipse([x - r * 0.5 - S, y - S, x - r * 0.5 + S, y + S], fill=(255, 250, 215, 255))
    im = _fin(big, W + 2 * pad, H)
    if p.get("glow") in (True, "1", 1, "true", "si"):
        im = _aura(im, col, W * 0.16, 0.8)
    return im


def _closed(pts, n=10):
    P = list(pts)
    Q = [P[-1]] + P + [P[0], P[1]]
    out = []
    for i in range(1, len(Q) - 2):
        for k in range(n):
            t = k / n
            out.append(tuple(0.5 * ((2 * Q[i][j]) + (-Q[i - 1][j] + Q[i + 1][j]) * t +
                                    (2 * Q[i - 1][j] - 5 * Q[i][j] + 4 * Q[i + 1][j] - Q[i + 2][j]) * t * t +
                                    (-Q[i - 1][j] + 3 * Q[i][j] - 3 * Q[i + 1][j] + Q[i + 2][j]) * t ** 3) for j in (0, 1)))
    return out


def _glass_shape(W, H, outline, glass, extra=None):
    """Silueta rellena tipo cristal: degradado, borde claro, brillo superior. outline en fracciones (x, y)."""
    from PIL import ImageFilter
    S = SS
    pts = [(x * W * S, y * H * S) for x, y in _closed(outline)]
    mask = Image.new("L", (W * S, H * S), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    yy = np.linspace(0, 1, H * S, dtype=np.float32)[:, None, None]
    top = np.array(_shade(glass, 1.45), np.float32)
    bot = np.array(_shade(glass, 0.8), np.float32)
    rgb = top * (1 - yy) + bot * yy
    rgb = np.broadcast_to(rgb, (H * S, W * S, 3)).astype(np.uint8)
    im = Image.fromarray(np.dstack([rgb, np.full((H * S, W * S), 255, np.uint8)]), "RGBA")
    im.putalpha(mask.point(lambda v: int(v * 0.62)))
    big = Image.new("RGBA", im.size, (0, 0, 0, 0))
    big.alpha_composite(im)
    dr = ImageDraw.Draw(big)
    dr.line(pts + [pts[0]], fill=(185, 232, 255, 245), width=int(S * 5), joint="curve")
    hl = Image.new("L", mask.size, 0)                                  # brillo interior suave en el borde superior
    ImageDraw.Draw(hl).line(pts[: len(pts) // 2], fill=120, width=int(S * 9))
    hl = hl.filter(ImageFilter.GaussianBlur(S * 4))
    hl = Image.composite(hl, Image.new("L", mask.size, 0), mask)
    white = Image.new("RGBA", mask.size, (230, 250, 255, 0))
    white.putalpha(hl)
    big.alpha_composite(white)
    return big, mask


def _offset(path, d):
    o = []
    for i, (x, y) in enumerate(path):
        a, b = path[max(0, i - 1)], path[min(len(path) - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dy) or 1
        o.append((x - dy / n * d, y + dx / n * d))
    return o


def _vessels(big, cen, gap, nerve=1.0, S=SS):
    dr = ImageDraw.Draw(big)
    dr.line(_offset(cen, gap), fill=(230, 50, 60, 255), width=int(S * 5), joint="curve")
    dr.line(_offset(cen, -gap), fill=(70, 120, 245, 255), width=int(S * 5), joint="curve")
    if nerve:
        dr.line(cen, fill=(255, 214, 63, int(255 * min(1, nerve))), width=int(S * 5), joint="curve")
    red = _offset(cen, gap)
    for i in range(3, len(red), 9):
        x, y = red[i]
        dr.ellipse([x - S * 5, y - S * 4, x + S * 5, y + S * 4], fill=(255, 130, 140, 255))


_FOOT = [(.10, .0), (.14, .22), (.08, .46), (.06, .70), (.12, .86), (.30, .88), (.42, .80), (.55, .87), (.78, .90),
         (.93, .88), (.99, .80), (.98, .68), (.90, .60), (.78, .52), (.62, .42), (.50, .30), (.42, .12), (.40, .0)]


def a_pie(w, p):
    """Pie de lado, de cristal, con talón, arco, dedos y nervio dorado por dentro (spark enciende chispas)."""
    W, H = int(w), int(w * 0.6)
    S = SS
    glass = _c(p.get("color"), (70, 130, 210))
    big, _m = _glass_shape(W, H, _FOOT, glass)
    dr = ImageDraw.Draw(big)
    for cx, cy, rw, rh in ((.945, .76, .04, .055), (.885, .79, .032, .045), (.83, .81, .029, .04), (.775, .83, .026, .036)):   # dedos
        dr.ellipse([(cx - rw) * W * S, (cy - rh) * H * S, (cx + rw) * W * S, (cy + rh) * H * S], outline=(185, 232, 255, 230), width=int(S * 3))
    dr.ellipse([.935 * W * S, .66 * H * S, .985 * W * S, .74 * H * S], fill=(235, 250, 255, 220))    # uña
    cen = _sm([(.25 * W * S, 0), (.26 * W * S, .34 * H * S), (.34 * W * S, .62 * H * S), (.50 * W * S, .72 * H * S), (.72 * W * S, .74 * H * S), (.92 * W * S, .72 * H * S)], 10)
    _vessels(big, cen, W * S * 0.018, 1.0)
    im = _fin(big, W, H)
    if p.get("spark") in (True, "1", 1, "true", "si"):
        im = _aura(im, (255, 214, 63), W * 0.04, 0.9)
    return _aura(im, (120, 200, 255), W * 0.03, 0.45)


_LEG = [(.04, .10), (.30, .08), (.56, .11), (.68, .15), (.73, .28), (.74, .52), (.76, .72), (.79, .79), (.90, .83), (.98, .86),
        (.98, .92), (.70, .94), (.52, .93), (.50, .82), (.51, .62), (.48, .44), (.40, .36), (.22, .34), (.05, .30)]


def a_pierna(w, p):
    """Pierna sentada vista de lado: muslo, rodilla, espinilla y pie, de cristal con arteria, vena y nervio."""
    W, H = int(w), int(w * 1.05)
    S = SS
    glass = _c(p.get("color"), (70, 130, 210))
    big, _m = _glass_shape(W, H, _LEG, glass)
    dr = ImageDraw.Draw(big)
    dr.ellipse([.60 * W * S, .13 * H * S, .70 * W * S, .26 * H * S], outline=(185, 232, 255, 200), width=int(S * 3))       # rótula
    dr.ellipse([.945 * W * S, .87 * H * S, .985 * W * S, .93 * H * S], fill=(235, 250, 255, 220))
    cen = _sm([(.08 * W * S, .20 * H * S), (.34 * W * S, .20 * H * S), (.58 * W * S, .22 * H * S), (.63 * W * S, .40 * H * S),
               (.63 * W * S, .68 * H * S), (.68 * W * S, .84 * H * S), (.88 * W * S, .90 * H * S)], 10)
    _vessels(big, cen, W * S * 0.022, float(p.get("nerve", 1) or 0))
    im = _fin(big, W, H)
    return _aura(im, (120, 200, 255), W * 0.03, 0.5)


# ----------------------------------------------------------------------------- SVG
_SVG_DIRS = None


def _svg_dirs():
    import os
    app = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return [os.path.join(app, "assets", "svg"), os.path.join(app, "cache", "svg_privados"), app, os.getcwd()]


def _svg_text(p):
    import os
    if p.get("svg"):
        return str(p["svg"])
    f = str(p.get("file") or "")
    if not f:
        raise ValueError("Elemento svg: falta «file» (en assets/svg/) o «svg» (texto).")
    cands = [f] if os.path.isabs(f) else [os.path.join(d, f if f.lower().endswith(".svg") else f + ".svg") for d in _svg_dirs()]
    for c in cands:
        if os.path.isfile(c):
            with open(c, encoding="utf-8") as fh:
                return fh.read()
    raise FileNotFoundError(f"No encuentro el SVG «{f}» (busqué en assets/svg/).")


def svg_prepare(text, p):
    """Sustituye {{variable|defecto}} y deja visibles solo las partes pedidas (only) o oculta otras (hide)."""
    import re as _re
    import xml.etree.ElementTree as ET
    text = _re.sub(r"\{\{\s*([\w-]+)\s*(?:\|([^}]*))?\}\}", lambda m: str(p.get(m.group(1), m.group(2) if m.group(2) is not None else "")), text)
    only = [x.strip() for x in str(p.get("only") or "").split(",") if x.strip()]
    hide = [x.strip() for x in str(p.get("hide") or "").split(",") if x.strip()]
    if only or hide:
        ET.register_namespace("", "http://www.w3.org/2000/svg")
        ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
        root = ET.fromstring(text)
        keep_tags = ("defs", "style", "title", "desc")
        for ch in list(root):
            tag = ch.tag.split("}")[-1]
            if tag in keep_tags:
                continue
            cid = ch.get("id", "")
            if (only and cid not in only) or (cid and cid in hide):
                root.remove(ch)
        text = ET.tostring(root, encoding="unicode")
    return text


def a_svg(w, p):
    """SVG propio (assets/svg/<file>.svg o texto en «svg»). Partes con id en <g>: only="nervio" / hide="huesos"; variables {{nombre|defecto}}."""
    try:
        import resvg_py
    except ImportError:
        import subprocess
        import sys
        try:        # la actualización automática no instala paquetes: se intenta una vez aquí
            subprocess.run([sys.executable, "-m", "pip", "install", "resvg-py"], check=True, capture_output=True, timeout=240)
            import resvg_py
        except Exception as e:
            raise RuntimeError("Falta el conversor de SVG: ejecuta  python -m pip install resvg-py  (o instalar.bat)") from e
    import io
    svg = svg_prepare(_svg_text(p), p)
    try:
        png = resvg_py.svg_to_bytes(svg_string=svg, width=int(w))
    except Exception as e:
        raise ValueError(f"SVG no válido: {e}") from e
    return Image.open(io.BytesIO(bytes(png))).convert("RGBA")


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
    "molecula": (a_molecula, 0.92, "Molécula de bolas y palitos con cara (trimetilamina)", "color, mood"),
    "burbuja_villano": (a_burbuja_villano, 1.0, "Burbuja con un villano diminuto adentro", "color"),
    "luz": (a_luz, 0.35, "Resplandor suave (luz bajo la puerta, foco)", "color, h"),
    "humo": (a_humo, 0.6, "Humo o niebla translúcida", "color"),
    "svg": (a_svg, 1.0, "Dibujo SVG propio: file (assets/svg/…), only/hide (partes con id), variables {{nombre}}", "file, only, hide, svg"),
    "gota": (a_gota, 1.3, "Gota de sangre", "color"),
    "globulo": (a_globulo, 0.82, "Glóbulo rojo (disco bicóncavo)", "color"),
    "rayo": (a_rayo, 1.6, "Rayo amarillo (señal eléctrica)", "color"),
    "hueso": (a_hueso, 0.34, "Hueso", "color"),
    "reloj": (a_reloj, 1.0, "Reloj analógico", "hour, min"),
    "cerebro": (a_cerebro, 0.85, "Cerebro rosa con circunvoluciones", "color, seed"),
    "nervio": (a_nervio, 1.6, "Nervio amarillo vertical con vainas", "color, pinch (0-1: punto aplastado), glow"),
    "pierna": (a_pierna, 1.05, "Pierna sentada translúcida con arteria, vena y nervio", "color, nerve (0-1)"),
    "pie": (a_pie, 0.6, "Pie translúcido con nervio dorado", "color, spark"),
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
