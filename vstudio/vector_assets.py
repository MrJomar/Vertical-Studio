"""Biblioteca de elementos vectoriales dibujados por código (sin descargas, sin licencias).

Cada elemento es una función (ancho_px, params) -> imagen RGBA. Se dibujan con suavizado y sombreado.
"""
from __future__ import annotations

import colorsys
import math
import random

import numpy as np
from PIL import ImageFilter
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
    """Persona de busto con volumen: cabeza esférica sombreada, peinados variados, mejillas, cejas y brillo de pelo."""
    W, H = int(w), int(w * 1.15)
    v = int(p.get("var", 0))
    rnd = random.Random(v * 7919 + 13)
    skins = [(247, 214, 186), (232, 180, 140), (198, 134, 96), (141, 90, 62), (96, 62, 44)]
    hairs = [(40, 28, 22), (90, 56, 30), (220, 176, 70), (170, 60, 40), (25, 25, 30), (150, 150, 160), (120, 60, 160)]
    shirts = [(214, 60, 90), (60, 140, 220), (120, 190, 80), (240, 160, 40), (150, 80, 200), (40, 170, 160), (230, 90, 50)]
    skin = _c(p.get("skin"), rnd.choice(skins))
    hair = _c(p.get("hair"), rnd.choice(hairs))
    shirt = _c(p.get("shirt"), rnd.choice(shirts))
    style = p.get("style") or rnd.choice(["corto", "largo", "rizado", "moño", "calvo", "flequillo", "gorro"])
    mood = p.get("mood") or rnd.choice(["happy", "happy", "happy", "neutral"])
    s = SS
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    cx = W * s / 2

    # torso con degradado vertical y hombros redondeados
    tw, th = int(W * s * 0.92), int(H * s * 0.62)
    gy = np.linspace(1.12, 0.7, th, dtype=np.float32)[:, None]
    gx = 1.0 - 0.22 * np.abs(np.linspace(-1, 1, tw, dtype=np.float32))[None, :] ** 2
    arr = np.clip(np.array(shirt, np.float32)[None, None, :] * (gy * gx)[..., None], 0, 255)
    torso = Image.fromarray(np.dstack([arr, np.full((th, tw), 255, np.float32)]).astype(np.uint8), "RGBA")
    tm = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(tm).rounded_rectangle([0, 0, tw, th * 2], radius=int(tw * 0.28), fill=255)
    torso.putalpha(tm)
    big.alpha_composite(torso, (int(cx - tw / 2), int(H * s * 0.58)))
    # cuello y cuello de la camisa
    dr.rectangle([cx - W * s * 0.09, H * s * 0.5, cx + W * s * 0.09, H * s * 0.66], fill=_shade(skin, 0.82) + (255,))
    dr.pieslice([cx - W * s * 0.16, H * s * 0.56, cx + W * s * 0.16, H * s * 0.76], 0, 180, fill=_shade(skin, 0.78) + (255,))

    # pelo de atrás
    if style == "largo":
        dr.rounded_rectangle([cx - W * s * 0.31, H * s * 0.14, cx + W * s * 0.31, H * s * 0.7], radius=W * s * 0.3,
                             fill=_shade(hair, 0.85) + (255,))
    elif style == "moño":
        dr.ellipse([cx - W * s * 0.12, H * s * 0.02, cx + W * s * 0.12, H * s * 0.2], fill=_shade(hair, 0.9) + (255,))
    elif style == "rizado":
        for ang in range(0, 360, 36):
            a = math.radians(ang)
            ccx, ccy = cx + math.cos(a) * W * s * 0.3, H * s * 0.38 + math.sin(a) * H * s * 0.24
            dr.ellipse([ccx - W * s * 0.1, ccy - W * s * 0.1, ccx + W * s * 0.1, ccy + W * s * 0.1],
                       fill=_shade(hair, 0.9) + (255,))

    # cabeza esférica con volumen
    hw, hh = int(W * s * 0.56), int(H * s * 0.5)
    head = sphere(hw, skin, spec=0.25, dark=0.62, light=(-0.35, -0.5)).resize((hw, hh), Image.LANCZOS)
    big.alpha_composite(head, (int(cx - hw / 2), int(H * s * 0.15)))
    hd = ImageDraw.Draw(big)

    # pelo delantero
    hcy = H * s * 0.4
    if style in ("corto", "moño", "gorro", "flequillo"):
        hd.chord([cx - W * s * 0.3, H * s * 0.1, cx + W * s * 0.3, H * s * 0.52], 180, 360, fill=hair + (255,))
        hd.arc([cx - W * s * 0.22, H * s * 0.13, cx + W * s * 0.02, H * s * 0.3], 200, 280,
               fill=_shade(hair, 1.6) + (255,), width=max(2, int(W * 0.018 * s)))
    if style == "flequillo":
        hd.chord([cx - W * s * 0.29, H * s * 0.15, cx + W * s * 0.29, H * s * 0.42], 180, 360, fill=hair + (255,))
    if style == "largo":
        hd.chord([cx - W * s * 0.3, H * s * 0.1, cx + W * s * 0.3, H * s * 0.5], 180, 360, fill=hair + (255,))
        hd.arc([cx - W * s * 0.2, H * s * 0.14, cx, H * s * 0.3], 200, 280, fill=_shade(hair, 1.6) + (255,),
               width=max(2, int(W * 0.018 * s)))
    if style == "rizado":
        for k in range(7):
            a = math.radians(200 + k * 23)
            ccx, ccy = cx + math.cos(a) * W * s * 0.22, H * s * 0.32 + math.sin(a) * H * s * 0.16
            hd.ellipse([ccx - W * s * 0.075, ccy - W * s * 0.075, ccx + W * s * 0.075, ccy + W * s * 0.075], fill=hair + (255,))
    if style == "gorro":
        gc = shirts[(v * 3 + 1) % len(shirts)]
        hd.chord([cx - W * s * 0.31, H * s * 0.08, cx + W * s * 0.31, H * s * 0.5], 180, 360, fill=gc + (255,))
        hd.rounded_rectangle([cx - W * s * 0.31, H * s * 0.27, cx + W * s * 0.31, H * s * 0.33], radius=W * s * 0.03,
                             fill=_shade(gc, 0.75) + (255,))
        hd.ellipse([cx - W * s * 0.05, H * s * 0.03, cx + W * s * 0.05, H * s * 0.13], fill=(250, 250, 250, 255))
    # orejas
    for sx in (-1, 1):
        hd.ellipse([cx + sx * W * s * 0.28 - W * s * 0.04, H * s * 0.38, cx + sx * W * s * 0.28 + W * s * 0.04, H * s * 0.48],
                   fill=_shade(skin, 0.9) + (255,))
    # ojos con brillo, cejas, mejillas y boca
    cheek = _canvas(W, H)
    yv = max(0.0, min(1.0, float(p.get("value", 1.0)))) if mood == "yawn" else 0.0
    for sx in (-1, 1):
        ex = cx + sx * W * s * 0.115
        if yv > 0.3:                                            # ojos cerrados con fuerza (bostezo)
            hd.arc([ex - W * s * 0.05, H * s * 0.385, ex + W * s * 0.05, H * s * 0.455], 15, 165, fill=(40, 28, 26, 255), width=max(2, int(W * 0.014 * s)))
            if yv > 0.75:                                       # lagrimita
                hd.ellipse([ex + sx * W * s * 0.045 - W * s * 0.011, H * s * 0.45, ex + sx * W * s * 0.045 + W * s * 0.011, H * s * 0.49], fill=(170, 220, 255, 230))
        else:
            hd.ellipse([ex - W * s * 0.04, H * s * 0.375, ex + W * s * 0.04, H * s * 0.455], fill=(255, 255, 255, 255))
            hd.ellipse([ex - W * s * 0.027, H * s * 0.39, ex + W * s * 0.027, H * s * 0.452], fill=(35, 25, 25, 255))
            hd.ellipse([ex - W * s * 0.014, H * s * 0.395, ex + W * s * 0.004, H * s * 0.415], fill=(255, 255, 255, 255))
        hd.arc([ex - W * s * 0.05, H * s * (0.33 - 0.022 * yv), ex + W * s * 0.05, H * s * (0.40 - 0.022 * yv)], 200, 340, fill=_shade(hair, 0.9) + (255,),
               width=max(2, int(W * 0.014 * s)))
        ImageDraw.Draw(cheek).ellipse([ex + sx * W * s * 0.03 - W * s * 0.04, H * s * 0.46,
                                       ex + sx * W * s * 0.03 + W * s * 0.04, H * s * 0.51], fill=(255, 110, 110, 70))
    big.alpha_composite(cheek)
    hd = ImageDraw.Draw(big)
    if mood == "yawn":                                          # boca que se abre con value: óvalo oscuro con lengua
        rx, ry = W * s * (0.04 + 0.05 * yv), H * s * (0.012 + 0.062 * yv)
        my = H * s * (0.515 + 0.012 * yv)
        hd.ellipse([cx - rx, my - ry, cx + rx, my + ry], fill=(105, 28, 38, 255), outline=(70, 20, 28, 255), width=max(2, int(W * 0.008 * s)))
        if yv > 0.35:
            hd.chord([cx - rx * 0.62, my + ry * 0.05, cx + rx * 0.62, my + ry * 0.98], 0, 180, fill=(205, 85, 100, 255))
    elif mood == "happy":
        hd.arc([cx - W * s * 0.1, H * s * 0.44, cx + W * s * 0.1, H * s * 0.56], 20, 160, fill=(130, 40, 45, 255),
               width=max(2, int(W * 0.016 * s)))
    else:
        hd.line([cx - W * s * 0.06, H * s * 0.52, cx + W * s * 0.06, H * s * 0.52], fill=(130, 40, 45, 255),
                width=max(2, int(W * 0.014 * s)))
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
    rn = r / R
    metal = 150 + 95 * np.clip(np.cos(np.radians(ang - 125)), -1, 1)            # luz desde arriba-izquierda
    metal = metal - 55 * np.clip((rn - 0.9) * 12, 0, 1) - 45 * np.exp(-((rn - 0.875) / 0.014) ** 2)   # ranura interior
    metal = metal + 55 * np.exp(-((rn - 0.975) / 0.012) ** 2)                      # bisel brillante exterior
    out[..., :3] = (metal[..., None] * np.array([0.96, 1.0, 1.08], np.float32)[None, None, :])
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
    # marcas de la escala y reflejo de cristal sobre la cara
    for k in range(15):
        aa = math.radians(180 - k * 180 / 14)
        r0, r1 = R * (0.77 if k % 7 else 0.74), R * 0.80
        dr.line([cx * s + r0 * s * math.cos(aa), cy * s - r0 * s * math.sin(aa), cx * s + r1 * s * math.cos(aa),
                 cy * s - r1 * s * math.sin(aa)], fill=(235, 235, 245, 200), width=max(2, int(W * 0.006 * s)))
    gl = _canvas(W, H)
    gd = ImageDraw.Draw(gl)
    gd.pieslice([(cx - R * 0.84) * s, (cy - R * 0.84) * s, (cx + R * 0.84) * s, (cy + R * 0.84) * s], 195, 345, fill=(255, 255, 255, 46))
    gd.ellipse([(cx - R * 0.9) * s, (cy - R * 0.62) * s, (cx + R * 0.9) * s, (cy + R * 1.2) * s], fill=(0, 0, 0, 0))
    big.alpha_composite(gl)
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
    up = bool(p.get("upper", True))
    if "\n" not in txt and p.get("fit", True):      # ajusta el tamaño para que quepa en UNA línea (nunca se parte ni se sale)
        t0 = text_layer(txt, "display", size, fill=fg, max_w=int(w * 6), upper=up)
        if t0.width > w * 0.9:
            size = max(8, int(size * w * 0.9 / t0.width))
    t = text_layer(txt, "display", size, fill=fg, max_w=int(w * 0.95), upper=up)
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
    size = int(p.get("size", w * 0.2))
    col, up = _c(p.get("color"), (255, 255, 255)), bool(p.get("upper", True))
    if p.get("fit") and "\n" not in txt:            # fit:true → una sola línea, reduciendo el tamaño si hace falta
        t0 = text_layer(txt, p.get("font", "display"), size, fill=col, stroke=int(p.get("stroke", 6)), max_w=int(w * 6), upper=up, shadow=4)
        if t0.width > w * 0.96:
            size = max(8, int(size * w * 0.96 / t0.width))
    return text_layer(txt, p.get("font", "display"), size, fill=col,
                      stroke=int(p.get("stroke", 6)), max_w=int(w), upper=up, shadow=4)


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
    """Pescado con volumen: lomo oscuro, flancos plateados, vientre claro, escamas, aletas translúcidas y ojo con iris."""
    from PIL import ImageFilter
    W, H = int(w), int(w * 0.56)
    body = _c(p.get("color"), (150, 170, 185))
    s = SS
    BW, BH = W * s, H * s
    # silueta del cuerpo (máscara)
    mk = Image.new("L", (BW, BH), 0)
    md = ImageDraw.Draw(mk)
    md.ellipse([0, BH * 0.2, BW * 0.86, BH * 0.8], fill=255)
    md.polygon([(BW * 0.72, BH * 0.36), (BW * 0.86, BH * 0.28), (BW * 0.86, BH * 0.72), (BW * 0.72, BH * 0.64)], fill=255)
    mask = np.asarray(mk, np.float32) / 255.0
    yy = (np.arange(BH, dtype=np.float32)[:, None] - BH * 0.2) / (BH * 0.6)          # 0 lomo → 1 vientre
    xx = np.arange(BW, dtype=np.float32)[None, :] / (BW * 0.86)
    yy = np.clip(yy, 0, 1)
    dorso = np.array(_shade(body, 0.42), np.float32)
    flanco = np.array(_shade(body, 1.05), np.float32)
    vientre = np.array([232, 240, 246], np.float32)
    t1 = np.clip(yy / 0.45, 0, 1)[..., None]
    t2 = np.clip((yy - 0.55) / 0.35, 0, 1)[..., None]
    col = dorso * (1 - t1) + flanco * t1
    col = col * (1 - t2) + vientre * t2
    col = col * (0.9 + 0.2 * np.clip(1 - xx, 0, 1))[..., None]       # más claro hacia la cabeza
    band = np.exp(-((yy - 0.42) / 0.06) ** 2)[..., None] * 70           # franja de brillo especular
    col = np.clip(col + band, 0, 255)
    im = Image.fromarray(np.dstack([col, mask * 255]).astype(np.uint8), "RGBA")
    big = _canvas(W, H)
    # aletas translúcidas con rayos
    fin = Image.new("RGBA", big.size, (0, 0, 0, 0))
    fd = ImageDraw.Draw(fin)
    fc = _shade(body, 0.62) + (235,)
    fd.polygon([(BW * 0.78, BH * 0.5), (BW, BH * 0.06), (BW * 0.97, BH * 0.5), (BW, BH * 0.94)], fill=fc)
    fd.polygon([(BW * 0.28, BH * 0.26), (BW * 0.46, BH * 0.0), (BW * 0.64, BH * 0.3)], fill=_shade(body, 0.55) + (240,))
    fd.polygon([(BW * 0.4, BH * 0.72), (BW * 0.52, BH * 0.95), (BW * 0.6, BH * 0.7)], fill=_shade(body, 0.6) + (230,))
    for k in range(6):
        f = k / 5
        fd.line([(BW * 0.8, BH * 0.5), (BW * 0.99, BH * (0.1 + 0.8 * f))], fill=_shade(body, 0.4) + (150,), width=max(2, int(BW * 0.003)))
    big.alpha_composite(fin)
    big.alpha_composite(im)
    # escamas: arcos suaves dentro del cuerpo
    sc = Image.new("RGBA", big.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(sc)
    r = BW * 0.045
    row = 0
    y = BH * 0.3
    while y < BH * 0.72:
        x = BW * 0.2 + (r if row % 2 else 0)
        while x < BW * 0.76:
            sd.arc([x - r, y - r, x + r, y + r], 300, 60, fill=(255, 255, 255, 70), width=max(2, int(r * 0.12)))
            x += r * 2
        y += r * 0.9
        row += 1
    sc.putalpha(Image.fromarray((np.asarray(sc.getchannel("A"), np.float32) * mask).astype(np.uint8)))
    big.alpha_composite(sc)
    bd = ImageDraw.Draw(big)
    bd.arc([BW * 0.24, BH * 0.3, BW * 0.38, BH * 0.7], 280, 80, fill=_shade(body, 0.5) + (255,), width=max(3, int(BW * 0.008)))
    bd.line([(BW * 0.15, BH * 0.5), (BW * 0.76, BH * 0.46)], fill=_shade(body, 0.7) + (120,), width=max(2, int(BW * 0.004)))
    # ojo con iris dorado y brillo
    ex, ey, er = BW * 0.1, BH * 0.42, BW * 0.036
    bd.ellipse([ex - er * 1.25, ey - er * 1.25, ex + er * 1.25, ey + er * 1.25], fill=(20, 24, 30, 255))
    bd.ellipse([ex - er, ey - er, ex + er, ey + er], fill=(238, 190, 70, 255))
    bd.ellipse([ex - er * 0.62, ey - er * 0.62, ex + er * 0.62, ey + er * 0.62], fill=(8, 8, 10, 255))
    bd.ellipse([ex - er * 0.45, ey - er * 0.7, ex - er * 0.05, ey - er * 0.3], fill=(255, 255, 255, 255))
    bd.arc([BW * 0.06, BH * 0.5, BW * 0.12, BH * 0.58], 20, 160, fill=_shade(body, 0.4) + (255,), width=max(2, int(BW * 0.004)))
    return _fin(big, W, H)


def a_gato(w, p):
    W, H = int(w), int(w * 1.15)
    fur = _c(p.get("color"), (236, 140, 48))
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    s = SS
    cx = W * s / 2
    er = p.get("mood") == "scared" or float(p.get("erizado", 0) or 0) > 0.5
    if er:       # pelo de punta alrededor de la cabeza, el cuerpo y la cola
        rr = random.Random(4)
        for (ccx, ccy, rx, ry, n, ln) in ((cx, H * s * 0.4, W * s * 0.4, H * s * 0.285, 34, 0.075),
                                          (cx, H * s * 0.76, W * s * 0.35, H * s * 0.245, 26, 0.07)):
            for i in range(n):
                a = 2 * math.pi * i / n + rr.uniform(-0.04, 0.04)
                if math.sin(a) > 0.2 and ccy < H * s * 0.5 and abs(math.cos(a)) < 0.55:
                    pass
                bx, by = ccx + rx * 0.94 * math.cos(a), ccy + ry * 0.94 * math.sin(a)
                tx, ty = ccx + (rx + W * s * ln * rr.uniform(0.8, 1.2)) * math.cos(a), ccy + (ry + W * s * ln * rr.uniform(0.8, 1.2)) * math.sin(a)
                hw = W * s * 0.018
                nx, ny = -math.sin(a) * hw, math.cos(a) * hw
                dr.polygon([(bx - nx, by - ny), (tx, ty), (bx + nx, by + ny)], fill=_shade(fur, 1.05) + (255,), outline=_shade(fur, 0.6) + (255,))
    dr.arc([cx + W * s * 0.04, H * s * 0.55, cx + W * s * 0.4, H * s * 0.98], 300, 120, fill=fur + (255,), width=int(W * (0.14 if er else 0.09) * s))
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
        pw = 0.012 if er else 0.03
        dr.ellipse([x - W * s * pw, H * s * 0.31, x + W * s * pw, H * s * 0.43], fill=(10, 10, 10, 255))
        dr.ellipse([x - W * s * 0.04, H * s * 0.32, x - W * s * 0.01, H * s * 0.36], fill=(255, 255, 255, 255))
        for k in (-1, 0, 1):
            dr.line([cx + sx * W * s * 0.1, H * s * 0.52 + k * 8, cx + sx * W * s * 0.5, H * s * 0.5 + k * 24], fill=(255, 255, 255, 230), width=4)
    dr.polygon([(cx - 12, H * s * 0.455), (cx + 12, H * s * 0.455), (cx, H * s * 0.485)], fill=(240, 120, 130, 255))
    if er:       # bufido: boca abierta con colmillos
        dr.ellipse([cx - W * s * 0.07, H * s * 0.49, cx + W * s * 0.07, H * s * 0.6], fill=(120, 24, 40, 255))
        for sx in (-1, 1):
            dr.polygon([(cx + sx * W * s * 0.045 - 8, H * s * 0.495), (cx + sx * W * s * 0.045 + 8, H * s * 0.495), (cx + sx * W * s * 0.045, H * s * 0.54)], fill=(255, 255, 255, 255))
        for sx in (-1, 1):
            xx = cx + sx * W * s * 0.17
            dr.polygon([(xx - sx * W * s * 0.1, H * s * 0.2), (xx + sx * W * s * 0.12, H * s * 0.27), (xx + sx * W * s * 0.12, H * s * 0.3), (xx - sx * W * s * 0.1, H * s * 0.25)], fill=_shade(fur, 0.45) + (255,))
    else:
        dr.arc([cx - 20, H * s * 0.48, cx, H * s * 0.52], 0, 180, fill=(120, 60, 40, 255), width=3)
        dr.arc([cx, H * s * 0.48, cx + 20, H * s * 0.52], 0, 180, fill=(120, 60, 40, 255), width=3)
    return _fin(big, W, H)


def a_hielo(w, p):
    """Cama de cubos de hielo translúcidos con bordes brillantes y destellos (borde inferior)."""
    W, H = int(w), int(w * 0.3)
    rnd = random.Random(5)
    s = SS
    big = _canvas(W, H)
    base = ImageDraw.Draw(big)
    base.rectangle([0, H * s * 0.45, W * s, H * s], fill=(150, 198, 226, 255))
    for layer, (lo, hi, y0, y1, tint) in enumerate(((0.22, 0.38, 0.12, 0.5, (170, 212, 236)), (0.28, 0.5, 0.0, 0.46, (205, 233, 249)))):
        x = -rnd.randint(0, 40)
        while x < W * s:
            sz = rnd.randint(int(H * s * lo), int(H * s * hi))
            y = H * s * rnd.uniform(y0, y1)
            cub = Image.new("RGBA", (sz + 6, sz + 6), (0, 0, 0, 0))
            cd = ImageDraw.Draw(cub)
            cd.rounded_rectangle([3, 3, sz + 2, sz + 2], radius=sz * 0.2, fill=tint + (225,), outline=(255, 255, 255, 235), width=max(2, int(sz * 0.05)))
            cd.polygon([(sz * 0.14, sz * 0.14), (sz * 0.62, sz * 0.14), (sz * 0.14, sz * 0.62)], fill=(255, 255, 255, 120))      # brillo diagonal
            cd.line([(sz * 0.7, sz * 0.88), (sz * 0.9, sz * 0.68)], fill=(120, 170, 215, 160), width=max(2, int(sz * 0.05)))
            cub = cub.rotate(rnd.uniform(-18, 18), Image.BICUBIC, expand=True)
            big.alpha_composite(cub, (int(x), int(y)))
            x += sz * rnd.uniform(0.55, 0.85)
    sp = ImageDraw.Draw(big)
    for _ in range(max(6, W // 60)):
        cx, cy, r = rnd.uniform(0, W * s), rnd.uniform(H * s * 0.1, H * s * 0.8), rnd.uniform(H * s * 0.02, H * s * 0.05)
        sp.polygon([(cx, cy - r * 2), (cx + r * 0.4, cy - r * 0.4), (cx + r * 2, cy), (cx + r * 0.4, cy + r * 0.4),
                    (cx, cy + r * 2), (cx - r * 0.4, cy + r * 0.4), (cx - r * 2, cy), (cx - r * 0.4, cy - r * 0.4)], fill=(255, 255, 255, 240))
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


def _laberinto(gw, gh, seed, steps=2000):
    """Patrón de Turing (Gray-Scott) en forma de laberinto: se parece mucho a las circunvoluciones del cerebro. Devuelve 0..1."""
    rng = np.random.default_rng(seed)
    U = np.ones((gh, gw), np.float32)
    V = np.zeros((gh, gw), np.float32)
    for _ in range(40):                                   # semillas
        y, x = rng.integers(8, gh - 8), rng.integers(8, gw - 8)
        V[y - 3:y + 3, x - 3:x + 3] = 1.0
        U[y - 3:y + 3, x - 3:x + 3] = 0.5
    V += rng.random((gh, gw)).astype(np.float32) * 0.02
    Fk, kk, du, dv = 0.037, 0.0600, 0.16, 0.08

    def lap(Z):
        return (np.roll(Z, 1, 0) + np.roll(Z, -1, 0) + np.roll(Z, 1, 1) + np.roll(Z, -1, 1) - 4 * Z)
    for _ in range(steps):
        uvv = U * V * V
        U += du * lap(U) - uvv + Fk * (1 - U)
        V += dv * lap(V) + uvv - (Fk + kk) * V
    V = (V - V.min()) / max(1e-6, (V.max() - V.min()))
    return V


def a_cerebro(w, p):
    """Cerebro de perfil (frente a la izquierda): circunvoluciones tipo laberinto, lóbulos con tinte, cerebelo y tronco."""
    from PIL import ImageFilter
    W, H = int(w), int(w * 0.85)
    S = SS
    col = _c(p.get("color"), (240, 150, 172))
    Ws, Hs = W * S, H * S
    P = lambda pts: [(x * Ws, y * Hs) for x, y in pts]
    outline = _sm(P([(0.07, 0.50), (0.045, 0.38), (0.075, 0.25), (0.17, 0.12), (0.31, 0.045), (0.48, 0.02), (0.66, 0.04),
                     (0.82, 0.11), (0.93, 0.23), (0.96, 0.38), (0.93, 0.52), (0.85, 0.60), (0.73, 0.62), (0.62, 0.60),
                     (0.55, 0.65), (0.47, 0.73), (0.36, 0.75), (0.25, 0.71), (0.18, 0.63), (0.11, 0.58), (0.07, 0.50)]), 10)
    mask = Image.new("L", (Ws, Hs), 0)
    ImageDraw.Draw(mask).polygon(outline, fill=255)
    out = _canvas(W, H)
    dk_line = _shade(col, 0.5) + (255,)
    # tronco encefálico (fino, inclinado hacia atrás)
    stem = Image.new("L", (Ws, Hs), 0)
    ImageDraw.Draw(stem).polygon(_sm(P([(0.47, 0.62), (0.56, 0.62), (0.585, 0.80), (0.62, 0.985), (0.545, 0.985), (0.50, 0.80)]), 8), fill=255)
    out.alpha_composite(_grad(stem, _shade(col, 0.88), _shade(col, 0.64), 0.6, 1.0))
    ImageDraw.Draw(out).line(_sm(P([(0.47, 0.64), (0.50, 0.80), (0.545, 0.985)]), 8), fill=dk_line, width=int(S * 2.4), joint="curve")
    ImageDraw.Draw(out).line(_sm(P([(0.56, 0.64), (0.585, 0.80), (0.62, 0.985)]), 8), fill=dk_line, width=int(S * 2.4), joint="curve")
    # cerebelo: metido bajo el lóbulo occipital, con láminas finas
    cb = Image.new("L", (Ws, Hs), 0)
    ImageDraw.Draw(cb).ellipse([Ws * 0.58, Hs * 0.56, Ws * 0.90, Hs * 0.84], fill=255)
    cbi = _grad(cb, _shade(col, 0.84), _shade(col, 0.56), 0.56, 0.84)
    dcb = ImageDraw.Draw(cbi)
    for k in range(9):
        y0 = Hs * (0.575 + 0.027 * k)
        dcb.arc([Ws * (0.55 + 0.012 * k), y0 - Hs * 0.16, Ws * 0.94, y0 + Hs * 0.32], 200, 335, fill=_shade(col, 0.42) + (190,), width=max(2, int(S * 1.8)))
    cbi.putalpha(cb)
    out.alpha_composite(cbi)
    ImageDraw.Draw(out).arc([Ws * 0.58, Hs * 0.56, Ws * 0.90, Hs * 0.84], 330, 120, fill=dk_line, width=int(S * 2.6))
    # circunvoluciones: patrón de Turing recortado por la forma
    gwid = 200
    pat = _laberinto(gwid, int(gwid * Hs / Ws), int(p.get("seed", 5)))
    pim = Image.fromarray((pat * 255).astype(np.uint8), "L").resize((Ws, Hs), Image.BICUBIC).filter(ImageFilter.GaussianBlur(Ws * 0.0025))
    r = np.asarray(pim, np.float32) / 255.0
    r = np.clip((r - 0.16) / 0.20, 0, 1)
    r = r * r * (3 - 2 * r)                                # 0 = surco, 1 = cresta
    lo, hi = np.array(_shade(col, 0.66), np.float32), np.array(_shade(col, 1.10), np.float32)
    rgb = lo[None, None, :] * (1 - r[..., None]) + hi[None, None, :] * r[..., None]
    # tinte suave por lóbulo
    yy, xx = np.mgrid[0:Hs, 0:Ws].astype(np.float32)
    xn, yn = xx / Ws, yy / Hs
    cs = 0.49 + 0.20 * (0.30 - yn)
    syl_y = 0.50 + 0.14 * (xn - 0.15)
    tem = ((yn > syl_y) & (xn < 0.66)).astype(np.uint8) * 255
    occ = ((xn > 0.77) & ~((yn > syl_y) & (xn < 0.62))).astype(np.uint8) * 255
    par = ((xn >= cs) & (xn <= 0.77) & ~((yn > syl_y) & (xn < 0.62))).astype(np.uint8) * 255
    mult = np.ones((Hs, Ws, 3), np.float32)
    for m, t in ((tem, (1.05, 0.92, 0.84)), (occ, (0.93, 0.90, 1.04)), (par, (1.0, 0.94, 0.92))):
        mf = np.asarray(Image.fromarray(m, "L").filter(ImageFilter.GaussianBlur(Ws * 0.03)), np.float32)[..., None] / 255.0
        mult += mf * (np.array(t, np.float32) - 1.0)
    rgb *= mult
    # volumen: más oscuro hacia el borde y luz arriba-izquierda
    inner = np.asarray(mask.filter(ImageFilter.GaussianBlur(Ws * 0.05)), np.float32) / 255.0
    rgb *= (0.55 + 0.45 * np.clip(inner * 1.4, 0, 1))[..., None]
    light = np.exp(-(((xn - 0.30) / 0.30) ** 2 + ((yn - 0.18) / 0.20) ** 2))[..., None]
    rgb = rgb + (255 - rgb) * 0.16 * light
    base = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), np.asarray(mask, np.float32)]).astype(np.uint8), "RGBA")
    out.alpha_composite(base)
    # surco lateral (fisura de Silvio): curva fina que se afina
    dd = ImageDraw.Draw(out)
    sl = _sm(P([(0.16, 0.555), (0.28, 0.525), (0.41, 0.545), (0.55, 0.585)]), 10)
    for i in range(len(sl) - 1):
        wdt = max(1, int(S * (4.2 - 3.4 * i / len(sl))))
        dd.line([sl[i], sl[i + 1]], fill=_shade(col, 0.40) + (235,), width=wdt)
    dd.line(outline + [outline[0]], fill=dk_line, width=int(S * 3), joint="curve")
    return _fin(out, W, H)


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
    try:
        txt = _svg_text(p)
    except FileNotFoundError:        # pieza aún no creada: marcador visible en vez de romper el render
        nom = str(p.get("file") or "pieza").replace("&", "").replace("<", "")
        txt = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 600"><rect x="30" y="40" width="460" height="520" rx="40" '
               'fill="#ffffff" fill-opacity=".06" stroke="#ffd23f" stroke-width="6" stroke-dasharray="26 18"/>'
               '<circle cx="260" cy="240" r="70" fill="none" stroke="#ffd23f" stroke-width="8"/>'
               '<path d="M225 240 h70 M260 205 v70" stroke="#ffd23f" stroke-width="8" stroke-linecap="round"/></svg>')
    svg = svg_prepare(txt, p)
    try:
        png = resvg_py.svg_to_bytes(svg_string=svg, width=int(w))
    except Exception as e:
        raise ValueError(f"SVG no válido: {e}") from e
    return Image.open(io.BytesIO(bytes(png))).convert("RGBA")


# ---------------------------------------------------------------- piezas nuevas: piel de gallina
def _grad(mask, top, bot, y0=0.0, y1=1.0):
    """RGBA con degradado vertical (top→bot entre las alturas relativas y0..y1), recortado por la máscara L."""
    w, h = mask.size
    t = np.clip((np.linspace(0, 1, h, dtype=np.float32) - y0) / max(1e-4, y1 - y0), 0, 1)[:, None, None]
    c0 = np.array(top[:3], np.float32)[None, None, :]
    c1 = np.array(bot[:3], np.float32)[None, None, :]
    rgb = np.broadcast_to(c0 * (1 - t) + c1 * t, (h, w, 3))
    return Image.fromarray(np.dstack([rgb, np.asarray(mask, np.float32)]).astype(np.uint8), "RGBA")


def _bez(p0, p1, p2, n=40):
    t = np.linspace(0, 1, n)[:, None]
    return ((1 - t) ** 2) * np.array(p0) + 2 * (1 - t) * t * np.array(p1) + (t ** 2) * np.array(p2)


def a_piel(w, p):
    """Corte de piel: epidermis, dermis, grasa, folículo con pelo y músculo erector. value 0 (relajada) → 1 (erizada)."""
    from PIL import ImageFilter
    W, H = int(w), int(w * 1.1)
    v = max(0.0, min(1.0, float(p.get("value", 0))))
    s = SS
    BW, BH = W * s, H * s
    rnd = random.Random(7)

    def P(x, y):
        return (x * BW, y * BH)

    X0, X1, YB, HX = 0.04, 0.96, 0.33, 0.50
    xs = np.linspace(X0, X1, 300)
    ys = YB - v * 0.07 * np.exp(-((xs - HX) / 0.10) ** 2) + 0.004 * np.sin(xs * 38)

    def band(top, bot):
        pts = [P(x, y) for x, y in zip(xs, top)] + [P(x, y) for x, y in zip(xs[::-1], bot[::-1])]
        m = Image.new("L", (BW, BH), 0)
        ImageDraw.Draw(m).polygon(pts, fill=255)
        return m

    y_epi = ys + 0.05
    y_der = np.full_like(xs, 0.76)
    y_fat = np.full_like(xs, 0.96)
    tissue = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
    tissue.alpha_composite(_grad(band(y_der, y_fat), (255, 220, 120), (240, 168, 56), 0.76, 0.96))
    tissue.alpha_composite(_grad(band(y_epi, y_der), (255, 156, 150), (214, 88, 108), YB, 0.76))
    tissue.alpha_composite(_grad(band(ys, y_epi), (255, 232, 206), (238, 180, 142), YB - 0.05, YB + 0.06))
    tex = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
    td = ImageDraw.Draw(tex)
    for _ in range(46):                                    # textura de la dermis
        x, y, r = rnd.uniform(0.07, 0.93), rnd.uniform(0.42, 0.74), rnd.uniform(0.004, 0.011)
        td.ellipse([(x - r) * BW, (y - r) * BH, (x + r) * BW, (y + r) * BH], fill=(150, 40, 70, 30))
    for k in range(13):                                    # células de grasa
        x, y, r = 0.09 + k * 0.067 + rnd.uniform(-0.01, 0.01), rnd.uniform(0.83, 0.9), rnd.uniform(0.026, 0.036)
        td.ellipse([(x - r) * BW, (y - r) * BH, (x + r) * BW, (y + r) * BH], fill=(255, 244, 190, 150), outline=(236, 160, 40, 190), width=max(2, int(BW * 0.004)))
    for yy, col in ((0.60, (210, 50, 70, 235)), (0.66, (70, 110, 220, 235))):   # vasos
        td.line([P(0.07, yy), P(0.24, yy)], fill=col, width=int(BW * 0.022))
        for xx in (0.07, 0.24):
            r = BW * 0.011
            td.ellipse([xx * BW - r, yy * BH - r, xx * BW + r, yy * BH + r], fill=col)
    tissue.alpha_composite(tex)
    clip = Image.new("L", (BW, BH), 0)
    ImageDraw.Draw(clip).rounded_rectangle([X0 * BW, (YB - 0.1) * BH, X1 * BW, 0.96 * BH], radius=int(0.045 * BW), fill=255)
    tissue.putalpha(Image.fromarray((np.asarray(tissue.getchannel("A"), np.float32) * np.asarray(clip, np.float32) / 255).astype(np.uint8)))
    big = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
    big.alpha_composite(tissue)
    d = ImageDraw.Draw(big)
    d.line([P(x, y) for x, y in zip(xs, ys)], fill=(255, 246, 232, 210), width=max(2, int(BW * 0.007)), joint="curve")   # brillo de la superficie

    # folículo: se endereza cuando el músculo se contrae
    ex, ey = HX, YB - v * 0.07 + 0.004 * math.sin(HX * 38)
    bulb = (0.28 + 0.17 * v, 0.62 + 0.06 * v)
    ctrl = ((ex + bulb[0]) / 2 + 0.035 * (1 - v), (ey + bulb[1]) / 2)
    fol = _bez((ex, ey + 0.02), ctrl, bulb, 50)
    d.line([P(x, y) for x, y in fol], fill=(255, 232, 214, 235), width=int(BW * 0.052), joint="curve")
    d.line([P(x, y) for x, y in fol], fill=(214, 150, 120, 255), width=int(BW * 0.006), joint="curve")
    br = BW * 0.05
    bx, by = P(*bulb)
    d.ellipse([bx - br, by - br, bx + br, by + br], fill=(255, 232, 214, 255), outline=(214, 150, 120, 255), width=max(2, int(BW * 0.005)))
    d.ellipse([bx - br * 0.45, by - br * 0.1, bx + br * 0.45, by + br * 0.7], fill=(230, 70, 90, 255))
    inner = fol[: int(len(fol) * 0.86)]
    d.line([P(x, y) for x, y in inner], fill=(70, 44, 30, 255), width=int(BW * 0.018), joint="curve")

    # pelo fuera de la piel
    a = math.radians(24 + 60 * v)
    L = 0.27 * BH
    e0 = P(ex, ey)
    tip = (e0[0] + L * math.cos(a), e0[1] - L * math.sin(a))
    ctl = (e0[0] + L * 0.55 * math.cos(a) - 0.05 * BW * (1 - v), e0[1] - L * 0.55 * math.sin(a) - 0.05 * BW * (1 - v) * 0.2)
    hair = _bez(e0, ctl, tip, 40)
    for i in range(len(hair) - 1):
        wd = int(BW * (0.03 - 0.018 * i / len(hair)))
        d.line([tuple(hair[i]), tuple(hair[i + 1])], fill=(64, 40, 30, 255), width=max(2, wd))
        d.line([tuple(hair[i] + (-wd * 0.18, 0)), tuple(hair[i + 1] + (-wd * 0.18, 0))], fill=(140, 96, 66, 200), width=max(1, wd // 4))

    # músculo erector: flojo y ondulado en reposo, tenso, grueso y rojo al contraerse
    t = 0.55
    A = tuple(np.array(_bez((ex, ey + 0.02), ctrl, bulb, 2)[0]) * 0 + _bez((ex, ey + 0.02), ctrl, bulb, 101)[int(t * 100)])
    B = (0.80, YB + 0.075)
    mid = ((A[0] + B[0]) / 2, (A[1] + B[1]) / 2 + 0.11 * (1 - v))
    mus = _bez(A, mid, B, 50)
    thick = BW * (0.020 + 0.016 * v)
    col_m = (int(200 + 55 * v), int(70 - 10 * v), int(92 - 28 * v), 255)
    if v > 0.45:
        glow = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
        ImageDraw.Draw(glow).line([P(x, y) for x, y in mus], fill=(255, 90, 90, int(150 * v)), width=int(thick * 2.6), joint="curve")
        big.alpha_composite(glow.filter(ImageFilter.GaussianBlur(BW * 0.012)))
        d = ImageDraw.Draw(big)
    d.line([P(x, y) for x, y in mus], fill=col_m, width=int(thick), joint="curve")
    d.line([P(x, y - 0.004) for x, y in mus], fill=(255, 190, 190, 150), width=max(2, int(thick * 0.28)), joint="curve")
    for pt in (A, B):
        r = thick * 0.62
        cxp, cyp = P(*pt)
        d.ellipse([cxp - r, cyp - r, cxp + r, cyp + r], fill=col_m)

    # nervio simpático con señal viajando hacia el músculo
    nerve = _bez((0.92, 0.95), (0.96, 0.58), (B[0] + 0.01, B[1] + 0.02), 60)
    d.line([P(x, y) for x, y in nerve], fill=(255, 214, 60, 255), width=int(BW * 0.011), joint="curve")
    if 0.0 < v < 0.97:
        f = min(1.0, v * 1.6)
        bx2, by2 = P(*nerve[int(f * (len(nerve) - 1))])
        gl = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
        r = BW * 0.03
        ImageDraw.Draw(gl).ellipse([bx2 - r, by2 - r, bx2 + r, by2 + r], fill=(255, 240, 120, 230))
        big.alpha_composite(gl.filter(ImageFilter.GaussianBlur(BW * 0.012)))
        d = ImageDraw.Draw(big)
        r = BW * 0.014
        d.ellipse([bx2 - r, by2 - r, bx2 + r, by2 + r], fill=(255, 255, 255, 255))
    return _fin(big, W, H)


def a_peludo(w, p):
    """Ancestro peludo: busto de homínido con pelaje, ceja marcada, cara clara y hombros anchos.
    erizado 0 (pelo caído) → 1 (pelo de punta). mood: neutral|happy|angry."""
    d = int(w)
    er = max(0.0, min(1.0, float(p.get("erizado", 0))))
    fur = _c(p.get("color"), (128, 80, 44))
    skin = (226, 182, 144)
    mood = p.get("mood", "neutral")
    S = SS
    D = d * S
    rnd = random.Random(int(p.get("var", 0)) + 11)
    im = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    big = _canvas(d, d)
    dr = ImageDraw.Draw(big)
    line = _shade(fur, 0.45) + (255,)

    def tufts(cx, cy, rx, ry, a0, a1, n, L, col, hw, layer_k):
        for i in range(n):
            ang = math.radians(a0 + (a1 - a0) * (i + 0.5) / n) + rnd.uniform(-0.04, 0.04)
            nx, ny = math.cos(ang), math.sin(ang)
            bx, by = cx + rx * nx, cy + ry * ny
            tx, ty = -ny, nx
            dx, dy = nx * (0.55 + 0.45 * er), ny * (0.55 + 0.45 * er) + (1 - er) * 0.95   # caído: tira hacia abajo; erizado: hacia fuera
            dn = math.hypot(dx, dy) or 1
            dx, dy = dx / dn, dy / dn
            ln = L * rnd.uniform(0.8, 1.15) * layer_k
            tip = (bx + dx * ln, by + dy * ln)
            mid = (bx + dx * ln * 0.5 + tx * ln * 0.12 * (1 if i % 2 else -1), by + dy * ln * 0.5 + ty * ln * 0.12 * (1 if i % 2 else -1))
            k = rnd.uniform(0.88, 1.12)
            dr.polygon([(bx - tx * hw, by - ty * hw), mid, tip, (mid[0] + tx * hw * 0.35, mid[1] + ty * hw * 0.35), (bx + tx * hw, by + ty * hw)],
                       fill=_shade(col, k) + (255,), outline=line)

    # ---- torso (hombros anchos) con mechones en el contorno
    tcx, tcy, trx, try_ = D * 0.5, D * 1.02, D * 0.43, D * 0.40
    L1 = D * (0.07 + 0.06 * er)
    tufts(tcx, tcy, trx, try_, 188, 352, 16, L1 * 1.2, _shade(fur, 0.72), D * 0.035, 1.0)
    dr.ellipse([tcx - trx, tcy - try_, tcx + trx, tcy + try_], fill=fur + (255,), outline=line, width=max(2, int(S * 2)))
    tufts(tcx, tcy, trx * 0.97, try_ * 0.97, 196, 344, 14, L1, fur, D * 0.03, 0.85)
    # ---- cabeza con mechones (arriba y a los lados)
    hcx, hcy, hr = D * 0.5, D * 0.40, D * 0.255
    L2 = D * (0.085 + 0.075 * er)
    tufts(hcx, hcy, hr, hr, 150, 390, 24, L2 * 1.15, _shade(fur, 0.7), D * 0.034, 1.0)
    im.alpha_composite(_fin(big, d, d))
    hd = int(hr * 2 / S)
    head = sphere(hd, fur, spec=0.08, dark=0.55, light=(-0.4, -0.5))
    layer = _canvas(hd, hd)
    d2 = ImageDraw.Draw(layer)
    r = hd * S / 2
    for _ in range(70):                                         # trazos de pelo sobre la cabeza
        x, y = rnd.uniform(0.0, 2.0) * r, rnd.uniform(0.0, 0.85) * r
        if (x - r) ** 2 + (y - r) ** 2 > (r * 0.95) ** 2:
            continue
        d2.line([x, y, x + rnd.uniform(-0.12, 0.12) * r, y + 0.2 * r], fill=_shade(fur, rnd.choice((0.65, 1.3))) + (170,), width=max(2, int(r * 0.03)))
    # cara clara (óvalo) con brillo suave
    fx0, fy0, fx1, fy1 = r * 0.30, r * 0.62, r * 1.70, r * 1.84
    d2.ellipse([fx0, fy0, fx1, fy1], fill=skin + (255,), outline=_shade(skin, 0.62) + (255,), width=max(2, int(r * 0.025)))
    # ceja marcada (arco grueso y oscuro) y ojos hundidos
    brow = _shade(fur, 0.42) + (255,)
    ey = r * 1.10
    for sx in (-1, 1):
        ex = r + sx * r * 0.36
        tilt = (0.16 if mood == "angry" else 0.0) * r
        d2.line([(ex - sx * r * 0.34, ey - r * 0.22 - (tilt if sx == -1 else tilt) * (-1 if sx == 1 else -1) * 0.0),
                 (ex, ey - r * 0.27 + tilt * 0.0), (ex + sx * r * 0.30, ey - r * 0.17 - (tilt if mood == "angry" else 0) * 0)],
                fill=brow, width=int(r * 0.15), joint="curve")
        d2.ellipse([ex - r * 0.15, ey - r * 0.11, ex + r * 0.15, ey + r * 0.11], fill=(255, 255, 255, 255), outline=_shade(skin, 0.5) + (255,), width=max(1, int(r * 0.012)))
        d2.ellipse([ex - r * 0.075, ey - r * 0.075, ex + r * 0.075, ey + r * 0.075], fill=(30, 20, 18, 255))
        d2.ellipse([ex - r * 0.03, ey - r * 0.055, ex + r * 0.012, ey - r * 0.015], fill=(255, 255, 255, 255))
    # nariz ancha
    d2.ellipse([r - r * 0.2, r * 1.28, r + r * 0.2, r * 1.52], fill=_shade(skin, 0.88) + (255,))
    for sx in (-1, 1):
        d2.ellipse([r + sx * r * 0.09 - r * 0.04, r * 1.40, r + sx * r * 0.09 + r * 0.04, r * 1.47], fill=_shade(skin, 0.45) + (255,))
    # boca
    my = r * 1.62
    if mood == "happy":
        d2.arc([r - r * 0.30, my - r * 0.20, r + r * 0.30, my + r * 0.16], 15, 165, fill=_shade(skin, 0.4) + (255,), width=int(r * 0.05))
    elif mood == "angry":
        d2.rounded_rectangle([r - r * 0.26, my - r * 0.04, r + r * 0.26, my + r * 0.15], radius=r * 0.06, fill=(90, 28, 30, 255), outline=_shade(skin, 0.4) + (255,), width=max(2, int(r * 0.02)))
        for k in range(4):
            tx_ = r - r * 0.2 + k * r * 0.133
            d2.polygon([(tx_, my - r * 0.03), (tx_ + r * 0.1, my - r * 0.03), (tx_ + r * 0.05, my + r * 0.06)], fill=(250, 246, 235, 255))
    else:
        d2.line([(r - r * 0.2, my), (r + r * 0.2, my)], fill=_shade(skin, 0.4) + (255,), width=int(r * 0.05))
    head.alpha_composite(_fin(layer, hd, hd))
    # orejas
    ear = _canvas(d, d)
    de = ImageDraw.Draw(ear)
    for sx in (-1, 1):
        ex_, ey_ = hcx + sx * hr * 0.97, hcy + hr * 0.12
        de.ellipse([ex_ - hr * 0.17, ey_ - hr * 0.2, ex_ + hr * 0.17, ey_ + hr * 0.2], fill=skin + (255,), outline=_shade(skin, 0.6) + (255,), width=max(2, int(S * 2)))
    im.alpha_composite(_fin(ear, d, d))
    im.alpha_composite(head, (int(hcx / S - hd / 2), int(hcy / S - hd / 2)))
    return im


def a_termometro(w, p):
    """Termómetro vertical con líquido que sube de azul (frío) a rojo (calor). value 0-1."""
    W, H = int(w), int(w * 2.3)
    v = max(0.0, min(1.0, float(p.get("value", 0.5))))
    s = SS
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    cx = W * s / 2
    tw = W * s * 0.26
    top, bcy, br = H * s * 0.03, H * s * 0.84, W * s * 0.27
    dr.rounded_rectangle([cx - tw, top, cx + tw, bcy], radius=tw, fill=(236, 246, 255, 215), outline=(255, 255, 255, 255), width=int(W * 0.02 * s))
    dr.ellipse([cx - br * 1.25, bcy - br * 1.0, cx + br * 1.25, bcy + br * 1.5], fill=(236, 246, 255, 215), outline=(255, 255, 255, 255), width=int(W * 0.02 * s))
    cold, hot = np.array((70, 160, 255)), np.array((255, 70, 56))
    col = tuple(int(x) for x in cold * (1 - v) + hot * v)
    ytop = (H * s * 0.78) * (1 - v) + (H * s * 0.12) * v
    cw = tw * 0.46
    dr.rounded_rectangle([cx - cw, ytop, cx + cw, bcy], radius=cw, fill=col + (255,))
    dr.ellipse([cx - br, bcy - br * 0.75, cx + br, bcy + br * 1.25], fill=col + (255,))
    dr.ellipse([cx - br * 0.55, bcy - br * 0.45, cx - br * 0.1, bcy], fill=(255, 255, 255, 150))
    dr.rounded_rectangle([cx - tw * 0.72, top + tw, cx - tw * 0.52, bcy - br * 0.4], radius=tw * 0.1, fill=(255, 255, 255, 130))
    for k in range(13):
        y = H * s * (0.14 + k * 0.05)
        ln = tw * (0.7 if k % 3 == 0 else 0.4)
        dr.line([cx + tw * 1.25, y, cx + tw * 1.25 + ln, y], fill=(235, 240, 250, 230), width=max(2, int(W * 0.012 * s)))
    return _fin(big, W, H)


def a_audifonos(w, p):
    """Audífonos de diadema."""
    W, H = int(w), int(w * 0.98)
    col = _c(p.get("color"), (236, 70, 112))
    s = SS
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    bw = int(W * 0.075 * s)
    dr.arc([W * s * 0.1, H * s * 0.02, W * s * 0.9, H * s * 1.0], 180, 360, fill=(46, 50, 70, 255), width=bw)
    dr.arc([W * s * 0.1, H * s * 0.02, W * s * 0.9, H * s * 1.0], 205, 335, fill=(120, 130, 170, 255), width=max(3, bw // 4))
    for sx in (0, 1):
        x0 = W * s * (0.02 if sx == 0 else 0.7)
        x1 = x0 + W * s * 0.28
        dr.rounded_rectangle([x0, H * s * 0.44, x1, H * s * 0.97], radius=W * s * 0.1, fill=_shade(col, 0.62) + (255,))
        dr.rounded_rectangle([x0 + W * s * 0.02, H * s * 0.46, x1 - W * s * 0.02, H * s * 0.9], radius=W * s * 0.09, fill=col + (255,))
        dr.rounded_rectangle([x0 + W * s * 0.05, H * s * 0.5, x0 + W * s * 0.11, H * s * 0.8], radius=W * s * 0.03, fill=_shade(col, 1.45) + (200,))
        cxm = (x0 + x1) / 2
        dr.ellipse([cxm - W * s * 0.06, H * s * 0.62, cxm + W * s * 0.06, H * s * 0.74], fill=_shade(col, 0.55) + (255,))
    return _fin(big, W, H)


def a_nota(w, p):
    """Nota musical brillante (double=true: dos notas unidas)."""
    W, H = int(w), int(w * 1.3)
    col = _c(p.get("color"), (255, 214, 70))
    s = SS
    big = _canvas(W, H)
    dr = ImageDraw.Draw(big)
    dark = _shade(col, 0.78) + (255,)
    edge = _shade(col, 0.5) + (255,)

    def head(cx, cy):
        im = Image.new("RGBA", (int(W * s * 0.5), int(W * s * 0.5)), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse([W * s * 0.02, W * s * 0.1, W * s * 0.48, W * s * 0.38], fill=col + (255,), outline=edge, width=max(3, int(W * 0.02 * s)))
        ImageDraw.Draw(im).ellipse([W * s * 0.1, W * s * 0.15, W * s * 0.26, W * s * 0.23], fill=_shade(col, 1.5) + (190,))
        im = im.rotate(22, Image.BICUBIC)
        big.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))

    if p.get("double"):
        pts = ((W * s * 0.28, H * s * 0.78), (W * s * 0.72, H * s * 0.68))
        for (x, y) in pts:
            head(x, y)
            dr.rectangle([x + W * s * 0.1, H * s * 0.2 + (y - pts[0][1]), x + W * s * 0.15, y], fill=dark)
        dr.polygon([(pts[0][0] + W * s * 0.1, H * s * 0.2), (pts[1][0] + W * s * 0.15, H * s * 0.1), (pts[1][0] + W * s * 0.15, H * s * 0.22), (pts[0][0] + W * s * 0.1, H * s * 0.32)], fill=dark)
    else:
        x, y = W * s * 0.34, H * s * 0.8
        head(x, y)
        dr.rectangle([x + W * s * 0.1, H * s * 0.1, x + W * s * 0.15, y], fill=dark)
        sx0, ty = x + W * s * 0.15, H * s * 0.1
        outer = _bez((sx0, ty), (sx0 + W * s * 0.5, ty + H * s * 0.12), (sx0 + W * s * 0.3, ty + H * s * 0.4), 24)
        inner = _bez((sx0 + W * s * 0.3, ty + H * s * 0.4), (sx0 + W * s * 0.34, ty + H * s * 0.2), (sx0, ty + H * s * 0.22), 24)
        dr.polygon([tuple(q) for q in outer] + [tuple(q) for q in inner], fill=dark)
    return _fin(big, W, H)



def a_pulmones(w, p):
    """Pulmones con tráquea y bronquios. value 0-1: qué tan inflados están."""
    W, H = int(w), int(w * 0.95)
    v = max(0.0, min(1.0, float(p.get("value", 0.5))))
    S = SS
    Ws, Hs = W * S, H * S
    col = _c(p.get("color"), (238, 132, 152))
    out = _canvas(W, H)
    k = 0.93 + 0.08 * v
    def lobe(sx):
        cx0 = 0.5 + sx * 0.235
        pts = [(cx0 - sx * 0.19 * k, 0.40), (cx0 - sx * 0.10 * k, 0.20), (cx0 + sx * 0.02, 0.17), (cx0 + sx * 0.12 * k, 0.30),
               (cx0 + sx * 0.20 * k, 0.55), (cx0 + sx * 0.18 * k, 0.80 + 0.02 * v), (cx0 + sx * 0.08 * k, 0.93 + 0.01 * v),
               (cx0 - sx * 0.12 * k, 0.92 + 0.01 * v), (cx0 - sx * 0.215 * k, 0.76), (cx0 - sx * 0.23 * k, 0.55)]
        return _sm([(x * Ws, y * Hs) for x, y in pts], 10)
    # tráquea con anillos
    tr = Image.new("L", (Ws, Hs), 0)
    ImageDraw.Draw(tr).rounded_rectangle([Ws * 0.455, Hs * 0.0, Ws * 0.545, Hs * 0.42], radius=Ws * 0.04, fill=255)
    out.alpha_composite(_grad(tr, (250, 214, 220), (214, 160, 176), 0.0, 0.42))
    dd = ImageDraw.Draw(out)
    for i in range(7):
        y = Hs * (0.04 + 0.052 * i)
        dd.arc([Ws * 0.455, y - Hs * 0.02, Ws * 0.545, y + Hs * 0.02], 0, 180, fill=(170, 110, 128, 255), width=max(2, int(S * 1.6)))
    for sx in (-1, 1):
        pts = lobe(sx)
        m = Image.new("L", (Ws, Hs), 0)
        ImageDraw.Draw(m).polygon(pts, fill=255)
        li = _grad(m, _shade(col, 1.14), _shade(col, 0.72), 0.15, 0.95)
        # bronquios (ramas claras) dentro del pulmón
        d2 = ImageDraw.Draw(li)
        bx0, by0 = Ws * 0.5, Hs * 0.40
        for (ex, ey, wd) in ((0.5 + sx * 0.12, 0.52, 7), (0.5 + sx * 0.20, 0.62, 5), (0.5 + sx * 0.15, 0.74, 5), (0.5 + sx * 0.25, 0.46, 4), (0.5 + sx * 0.19, 0.84, 4)):
            pth = [tuple(map(float, q)) for q in _bez((bx0, by0), (Ws * (0.5 + sx * 0.05), Hs * ey), (Ws * ex, Hs * ey), 14)]
            d2.line(pth, fill=(255, 226, 232, 210), width=max(2, int(S * wd * 0.8)), joint="curve")
        li.putalpha(m)
        out.alpha_composite(li)
        ImageDraw.Draw(out).line(pts + [pts[0]], fill=_shade(col, 0.5) + (255,), width=int(S * 2.6), joint="curve")
        hl = Image.new("L", (Ws, Hs), 0)
        ImageDraw.Draw(hl).ellipse([Ws * (0.5 + sx * 0.33 - 0.05), Hs * 0.3, Ws * (0.5 + sx * 0.33 + 0.05), Hs * 0.52], fill=110)
        hl = Image.fromarray((np.asarray(hl.filter(ImageFilter.GaussianBlur(Ws * 0.02)), np.float32) * (np.asarray(m, np.float32) / 255)).astype(np.uint8), "L")
        out.alpha_composite(Image.merge("RGBA", (*Image.new("RGB", (Ws, Hs), (255, 235, 240)).split(), hl)))
    return _fin(out, W, H)


def a_aire(w, p):
    """Corrientes de aire (viento) con remolinos. color azul claro por defecto."""
    W, H = int(w), int(w * 0.5)
    S = SS
    Ws, Hs = W * S, H * S
    col = _c(p.get("color"), (190, 232, 255))
    out = _canvas(W, H)
    dr = ImageDraw.Draw(out)
    rows = ((0.30, 0.0, 0.96, 0.17), (0.60, 0.06, 0.9, 0.15), (0.88, 0.0, 0.78, 0.15))
    for (y, x0, x1, curl) in rows:
        n = 40
        pts = []
        for i in range(n + 1):
            t = i / n
            pts.append(((x0 + (x1 - x0) * t) * Ws, (y + 0.05 * math.sin(t * 6.283 * 1.2)) * Hs))
        # remolino al final
        cx_, cy_ = pts[-1][0], pts[-1][1] - curl * Hs
        for i in range(1, 26):
            a = math.radians(90 + i * 14)
            r_ = curl * Hs * (1 - i / 34)
            pts.append((cx_ + math.cos(a) * r_ + 0.0, cy_ + math.sin(a) * r_))
        for i in range(len(pts) - 1):
            t = i / len(pts)
            wd = max(2, int(S * (3 + 12 * math.sin(math.pi * min(1.0, t * 1.15)) * 0.9)))
            al = int(255 * (0.35 + 0.65 * math.sin(math.pi * min(1.0, t * 1.05))))
            dr.line([pts[i], pts[i + 1]], fill=col + (al,), width=wd)
            dr.ellipse([pts[i + 1][0] - wd / 2, pts[i + 1][1] - wd / 2, pts[i + 1][0] + wd / 2, pts[i + 1][1] + wd / 2], fill=col + (al,))
    return _fin(out, W, H)


def a_perro(w, p):
    """Perro sentado de frente (orejas caídas). mood: normal | yawn (ojos cerrados, boca abierta con lengua)."""
    W, H = int(w), int(w * 1.1)
    S = SS
    Ws, Hs = W * S, H * S
    fur = _c(p.get("color"), (212, 158, 96))
    dark = _shade(fur, 0.62)
    yawn = p.get("mood") == "yawn"
    out = _canvas(W, H)
    dr = ImageDraw.Draw(out)
    line = _shade(fur, 0.45) + (255,)
    lw = max(2, int(S * 2.4))
    # cola (atrás)
    dr.arc([Ws * 0.66, Hs * 0.62, Ws * 0.98, Hs * 0.98], 250, 40, fill=dark + (255,), width=int(Ws * 0.06))
    # cuerpo sentado
    body = Image.new("L", (Ws, Hs), 0)
    ImageDraw.Draw(body).ellipse([Ws * 0.2, Hs * 0.5, Ws * 0.8, Hs * 1.04], fill=255)
    out.alpha_composite(_grad(body, _shade(fur, 1.08), _shade(fur, 0.74), 0.5, 1.0))
    dr = ImageDraw.Draw(out)
    dr.ellipse([Ws * 0.36, Hs * 0.62, Ws * 0.64, Hs * 0.98], fill=(250, 232, 205, 255))      # pecho claro
    for sx in (-1, 1):                                                                      # patas delanteras
        px = Ws * (0.5 + sx * 0.12)
        dr.rounded_rectangle([px - Ws * 0.055, Hs * 0.74, px + Ws * 0.055, Hs * 0.98], radius=Ws * 0.05, fill=_shade(fur, 1.05) + (255,), outline=line, width=lw)
        dr.ellipse([px - Ws * 0.07, Hs * 0.92, px + Ws * 0.07, Hs * 1.0], fill=(250, 232, 205, 255), outline=line, width=lw)
    # orejas caídas (detrás de la cabeza)
    for sx in (-1, 1):
        ex = Ws * (0.5 + sx * 0.27)
        dr.polygon(_sm([(Ws * 0.5 + sx * Ws * 0.19, Hs * 0.16), (ex + sx * Ws * 0.06, Hs * 0.2), (ex + sx * Ws * 0.09, Hs * 0.40),
                        (ex + sx * Ws * 0.03, Hs * 0.5), (ex - sx * Ws * 0.03, Hs * 0.38)], 8), fill=dark + (255,), outline=line)
    # cabeza
    hd = int(Ws * 0.56)
    head = sphere(int(hd / S), fur, spec=0.12, dark=0.62, light=(-0.35, -0.5)).resize((int(hd / S) * S // S, int(hd / S * 0.92)))
    hs = _canvas(W, H)
    hs.alpha_composite(head.resize((hd, int(hd * 0.92)), Image.LANCZOS), (int(Ws * 0.5 - hd / 2), int(Hs * 0.13)))
    out.alpha_composite(hs)
    dr = ImageDraw.Draw(out)
    # hocico claro
    my0 = Hs * 0.38
    dr.ellipse([Ws * 0.36, my0, Ws * 0.64, my0 + Hs * 0.2], fill=(250, 232, 205, 255), outline=_shade(fur, 0.7) + (255,), width=max(2, int(S * 1.5)))
    dr.ellipse([Ws * 0.455, my0 + Hs * 0.005, Ws * 0.545, my0 + Hs * 0.06], fill=(40, 28, 26, 255))                # nariz
    dr.ellipse([Ws * 0.47, my0 + Hs * 0.012, Ws * 0.50, my0 + Hs * 0.025], fill=(255, 255, 255, 190))
    dr.line([Ws * 0.5, my0 + Hs * 0.06, Ws * 0.5, my0 + Hs * 0.09], fill=(60, 40, 36, 255), width=max(2, int(S * 1.8)))
    if yawn:
        dr.ellipse([Ws * 0.425, my0 + Hs * 0.075, Ws * 0.575, my0 + Hs * 0.2], fill=(105, 28, 38, 255), outline=(70, 20, 28, 255), width=max(2, int(S * 1.6)))
        dr.chord([Ws * 0.44, my0 + Hs * 0.12, Ws * 0.56, my0 + Hs * 0.2], 0, 180, fill=(232, 110, 128, 255))
        for sx in (-1, 1):                                                                  # colmillos
            dr.polygon([(Ws * (0.5 + sx * 0.05), my0 + Hs * 0.082), (Ws * (0.5 + sx * 0.075), my0 + Hs * 0.082), (Ws * (0.5 + sx * 0.062), my0 + Hs * 0.12)], fill=(252, 250, 240, 255))
    else:
        dr.arc([Ws * 0.44, my0 + Hs * 0.06, Ws * 0.5, my0 + Hs * 0.12], 10, 170, fill=(60, 40, 36, 255), width=max(2, int(S * 1.8)))
        dr.arc([Ws * 0.5, my0 + Hs * 0.06, Ws * 0.56, my0 + Hs * 0.12], 10, 170, fill=(60, 40, 36, 255), width=max(2, int(S * 1.8)))
    # ojos y cejas
    for sx in (-1, 1):
        ex, ey = Ws * (0.5 + sx * 0.12), Hs * 0.3
        if yawn:
            dr.arc([ex - Ws * 0.045, ey - Hs * 0.02, ex + Ws * 0.045, ey + Hs * 0.035], 15, 165, fill=(40, 28, 26, 255), width=max(2, int(S * 2.4)))
        else:
            dr.ellipse([ex - Ws * 0.042, ey - Hs * 0.04, ex + Ws * 0.042, ey + Hs * 0.04], fill=(255, 255, 255, 255), outline=line, width=max(1, int(S * 1.2)))
            dr.ellipse([ex - Ws * 0.026, ey - Hs * 0.026, ex + Ws * 0.026, ey + Hs * 0.03], fill=(40, 28, 26, 255))
            dr.ellipse([ex - Ws * 0.016, ey - Hs * 0.022, ex - Ws * 0.002, ey - Hs * 0.006], fill=(255, 255, 255, 255))
        dr.arc([ex - Ws * 0.055, ey - Hs * 0.085, ex + Ws * 0.055, ey - Hs * 0.03], 200, 340, fill=dark + (255,), width=max(2, int(S * 2.2)))
    return _fin(out, W, H)


def a_bebe(w, p):
    """Bebé dentro de una burbuja de útero (líquido amniótico). value 0-1: apertura del bostezo."""
    W = H = int(w)
    S = SS
    Ws = W * S
    yv = max(0.0, min(1.0, float(p.get("value", 1.0))))
    skin = _c(p.get("skin"), (250, 200, 176))
    out = _canvas(W, H)
    dr = ImageDraw.Draw(out)
    bub = Image.new("L", (Ws, Ws), 0)
    ImageDraw.Draw(bub).ellipse([Ws * 0.02, Ws * 0.02, Ws * 0.98, Ws * 0.98], fill=255)
    out.alpha_composite(_grad(bub, (255, 188, 190), (214, 112, 140), 0.0, 1.0))
    glow = Image.new("L", (Ws, Ws), 0)
    ImageDraw.Draw(glow).ellipse([Ws * 0.25, Ws * 0.2, Ws * 0.75, Ws * 0.7], fill=170)
    glow = Image.fromarray((np.asarray(glow.filter(ImageFilter.GaussianBlur(Ws * 0.09)), np.float32) * (np.asarray(bub, np.float32) / 255)).astype(np.uint8), "L")
    out.alpha_composite(Image.merge("RGBA", (*Image.new("RGB", (Ws, Ws), (255, 232, 210)).split(), glow)))
    inner = _canvas(W, H)
    dr = ImageDraw.Draw(inner)
    # hombros / cuerpo y manitas
    dr.ellipse([Ws * 0.2, Ws * 0.66, Ws * 0.8, Ws * 1.1], fill=_shade(skin, 0.95) + (255,), outline=_shade(skin, 0.7) + (255,), width=int(S * 2.4))
    cx = Ws / 2
    hd = int(Ws * 0.46)
    head = sphere(int(hd / S), skin, spec=0.2, dark=0.7, light=(-0.35, -0.5)).resize((hd, hd), Image.LANCZOS)
    inner.alpha_composite(head, (int(cx - hd / 2), int(Ws * 0.2)))
    dr = ImageDraw.Draw(inner)
    hy = Ws * 0.2 + hd * 0.5
    dr.arc([cx - hd * 0.12, Ws * 0.2, cx + hd * 0.12, Ws * 0.2 + hd * 0.16], 200, 340, fill=_shade(skin, 0.55) + (255,), width=int(S * 2.2))   # un rizo
    cheek = _canvas(W, H)
    dc = ImageDraw.Draw(cheek)
    for sx in (-1, 1):
        ex = cx + sx * hd * 0.2
        dr.arc([ex - hd * 0.09, hy - hd * 0.06, ex + hd * 0.09, hy + hd * 0.08], 15, 165, fill=(70, 40, 36, 255), width=max(2, int(S * 2.4)))
        dc.ellipse([ex + sx * hd * 0.1 - hd * 0.09, hy + hd * 0.1, ex + sx * hd * 0.1 + hd * 0.09, hy + hd * 0.24], fill=(255, 120, 120, 80))
        hx = cx + sx * hd * 0.5                                                         # manita junto a la cara
        dr.ellipse([hx - hd * 0.1, hy + hd * 0.28, hx + hd * 0.1, hy + hd * 0.48], fill=_shade(skin, 1.03) + (255,), outline=_shade(skin, 0.65) + (255,), width=max(2, int(S * 2)))
    inner.alpha_composite(cheek)
    dr = ImageDraw.Draw(inner)
    rx, ry = hd * (0.05 + 0.08 * yv), hd * (0.025 + 0.1 * yv)
    my = hy + hd * 0.26
    dr.ellipse([cx - rx, my - ry, cx + rx, my + ry], fill=(160, 56, 70, 255), outline=(110, 36, 50, 255), width=max(2, int(S * 1.6)))
    # cordón umbilical
    cord = [tuple(map(float, q)) for q in _bez((cx, Ws * 0.98), (cx - Ws * 0.18, Ws * 0.82), (cx - Ws * 0.28, Ws * 0.6), 30)]
    for i in range(len(cord) - 1):
        dr.line([cord[i], cord[i + 1]], fill=(246, 214, 222, 255) if (i // 3) % 2 == 0 else (226, 170, 190, 255), width=int(S * 5))
    # recorta todo lo de dentro con la burbuja
    ia = np.asarray(inner.getchannel("A"), np.float32) * (np.asarray(bub, np.float32) / 255.0)
    inner.putalpha(Image.fromarray(ia.astype(np.uint8), "L"))
    out.alpha_composite(inner)
    ImageDraw.Draw(out).ellipse([Ws * 0.02, Ws * 0.02, Ws * 0.98, Ws * 0.98], outline=(255, 255, 255, 190), width=int(S * 3))
    return _fin(out, W, H)



def _clamp01(v, d=0.0):
    try:
        return max(0.0, min(1.0, float(v)))
    except Exception:
        return d


def _clipto(layer, ref):
    """Recorta layer (RGBA) con el alfa de ref (RGBA o L)."""
    from PIL import ImageChops
    m = ref if ref.mode == "L" else ref.getchannel("A")
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), m))
    return layer


def a_frasco(w, p):
    """Frasco de miel con tapa y etiqueta. nivel 0-1, cristal 0-1 (miel cristalizada), burbujas 0-1 (fermentando), tapa true|false."""
    W, H = int(w), int(w * 1.25)
    S = SS
    Ws, Hs = W * S, H * S
    nivel = _clamp01(p.get("nivel", 0.85))
    cri = _clamp01(p.get("cristal", 0))
    bub = _clamp01(p.get("burbujas", 0))
    tapa = p.get("tapa", True) not in (False, "false", 0, "0")
    lid = _c(p.get("color"), (205, 62, 50))
    rnd = random.Random(11)

    def shape(inset=0.0):
        m = Image.new("L", (Ws, Hs), 0)
        d = ImageDraw.Draw(m)
        i = Ws * inset
        d.rounded_rectangle([Ws * 0.12 + i, Hs * 0.2 + i, Ws * 0.88 - i, Hs * 0.97 - i], radius=Ws * 0.14, fill=255)
        d.rectangle([Ws * 0.23 + i, Hs * 0.1, Ws * 0.77 - i, Hs * 0.3], fill=255)
        return m

    glass = shape(0)
    inner = shape(0.03)
    ytop = Hs * 0.97 - nivel * (Hs * 0.97 - Hs * 0.16)
    cut = Image.new("L", (Ws, Hs), 0)
    ImageDraw.Draw(cut).rectangle([0, ytop, Ws, Hs], fill=255)
    from PIL import ImageChops
    hm = ImageChops.multiply(inner, cut)
    top_c = (255, 205, 80) if cri < 0.5 else (244, 214, 128)
    bot_c = (214, 118, 18) if cri < 0.5 else (226, 168, 66)
    out = _canvas(W, H)
    # fondo de vidrio
    gl = Image.new("RGBA", (Ws, Hs), (225, 240, 255, 55))
    out.alpha_composite(_clipto(gl, glass))
    hon = _grad(hm, top_c, bot_c, ytop / Hs, 1.0)
    out.alpha_composite(hon)
    lay = Image.new("RGBA", (Ws, Hs), (0, 0, 0, 0))
    dl = ImageDraw.Draw(lay)
    # superficie
    dl.ellipse([Ws * 0.15, ytop - Hs * 0.018, Ws * 0.85, ytop + Hs * 0.022], fill=(255, 230, 140, 200))
    if bub > 0:
        for _ in range(int(6 + 26 * bub)):
            bx = rnd.uniform(0.17, 0.83) * Ws
            by = rnd.uniform(ytop + Hs * 0.01, Hs * 0.94)
            br = rnd.uniform(0.012, 0.034 + 0.01 * bub) * Ws
            dl.ellipse([bx - br, by - br, bx + br, by + br], fill=(255, 245, 205, 150), outline=(255, 255, 255, 220), width=max(1, S))
            dl.ellipse([bx - br * 0.5, by - br * 0.6, bx - br * 0.1, by - br * 0.2], fill=(255, 255, 255, 230))
        for _ in range(int(8 * bub)):
            bx = rnd.uniform(0.17, 0.83) * Ws
            br = rnd.uniform(0.02, 0.04) * Ws
            dl.ellipse([bx - br, ytop - br * 1.3, bx + br, ytop + br * 0.4], fill=(255, 248, 220, 235), outline=(255, 255, 255, 255), width=max(1, S))
    if cri > 0:
        for _ in range(int(900 * cri)):
            gx = rnd.uniform(0.15, 0.85) * Ws
            gy = rnd.uniform(max(ytop, Hs * 0.2), Hs * 0.95)
            gr = rnd.uniform(0.004, 0.011) * Ws
            col = rnd.choice([(255, 238, 170, 210), (236, 190, 90, 200), (255, 250, 214, 190)])
            dl.ellipse([gx - gr, gy - gr, gx + gr, gy + gr], fill=col)
    out.alpha_composite(_clipto(lay, inner))
    dr = ImageDraw.Draw(out)
    lw = max(2, int(S * 2.6))
    # contorno de vidrio
    edge = Image.new("L", (Ws, Hs), 0)
    ImageDraw.Draw(edge).rectangle([0, 0, Ws, Hs], fill=255)
    ring = ImageChops.subtract(glass, shape(0.012))
    out.alpha_composite(_clipto(Image.new("RGBA", (Ws, Hs), (255, 255, 255, 235)), ring))
    # etiqueta con panal
    dr.rounded_rectangle([Ws * 0.22, Hs * 0.5, Ws * 0.78, Hs * 0.8], radius=Ws * 0.04, fill=(255, 246, 222, 245), outline=(150, 92, 30, 255), width=lw)
    cx, cy, rr = Ws * 0.5, Hs * 0.65, Ws * 0.1
    for k, (ox, oy) in enumerate([(0, 0), (-1.75, 0), (1.75, 0), (-0.88, -1.5), (0.88, -1.5), (-0.88, 1.5), (0.88, 1.5)]):
        pts = [(cx + ox * rr * 0.62 + rr * 0.58 * math.cos(math.radians(60 * i + 30)), cy + oy * rr * 0.62 + rr * 0.58 * math.sin(math.radians(60 * i + 30))) for i in range(6)]
        dr.polygon(pts, fill=(255, 190, 40, 255) if k == 0 else (255, 214, 110, 255), outline=(150, 92, 30, 255))
    # brillos
    dr.rounded_rectangle([Ws * 0.17, Hs * 0.3, Ws * 0.215, Hs * 0.9], radius=Ws * 0.025, fill=(255, 255, 255, 105))
    dr.rounded_rectangle([Ws * 0.81, Hs * 0.34, Ws * 0.835, Hs * 0.62], radius=Ws * 0.012, fill=(255, 255, 255, 70))
    # tapa
    if tapa:
        dr.rounded_rectangle([Ws * 0.2, Hs * 0.025, Ws * 0.8, Hs * 0.135], radius=Ws * 0.035, fill=_shade(lid, 0.66) + (255,))
        dr.rounded_rectangle([Ws * 0.2, Hs * 0.025, Ws * 0.8, Hs * 0.115], radius=Ws * 0.035, fill=lid + (255,), outline=_shade(lid, 0.5) + (255,), width=lw)
        for k in range(9):
            x = Ws * (0.255 + k * 0.061)
            dr.line([x, Hs * 0.04, x, Hs * 0.108], fill=_shade(lid, 0.74) + (255,), width=max(2, int(S * 1.6)))
        dr.rounded_rectangle([Ws * 0.24, Hs * 0.034, Ws * 0.3, Hs * 0.1], radius=Ws * 0.02, fill=_shade(lid, 1.35) + (190,))
    else:
        dr.ellipse([Ws * 0.23, Hs * 0.085, Ws * 0.77, Hs * 0.12], outline=(255, 255, 255, 235), width=lw)
    return _fin(out, W, H)


def a_abeja(w, p):
    """Abejita de frente con alas translúcidas, rayas, antenas y sonrisa."""
    W, H = int(w), int(w * 0.95)
    S = SS
    Ws, Hs = W * S, H * S
    yel = _c(p.get("color"), (255, 200, 40))
    out = Image.new("RGBA", (Ws, Hs), (0, 0, 0, 0))
    dr = ImageDraw.Draw(out)
    lw = max(2, int(S * 2.2))
    # alas
    wings = Image.new("RGBA", (Ws, Hs), (0, 0, 0, 0))
    dw = ImageDraw.Draw(wings)
    for sx in (-1, 1):
        cx = Ws * (0.5 + sx * 0.28)
        dw.ellipse([cx - Ws * 0.2, Hs * 0.12, cx + Ws * 0.2, Hs * 0.5], fill=(200, 232, 255, 150), outline=(255, 255, 255, 230), width=lw)
        dw.ellipse([cx - Ws * 0.1, Hs * 0.18, cx - Ws * 0.02 if sx > 0 else cx + Ws * 0.0, Hs * 0.3], fill=(255, 255, 255, 120))
    wings = wings.rotate(0)
    out.alpha_composite(wings)
    # aguijón
    dr.polygon([(Ws * 0.46, Hs * 0.9), (Ws * 0.54, Hs * 0.9), (Ws * 0.5, Hs * 0.99)], fill=(40, 30, 24, 255))
    # cuerpo
    bw, bh = int(Ws * 0.5), int(Hs * 0.56)
    body = sphere(int(bw / S), yel, spec=0.45, dark=0.55).resize((bw, bh), Image.LANCZOS)
    bl = Image.new("RGBA", (Ws, Hs), (0, 0, 0, 0))
    bl.alpha_composite(body, (int(Ws * 0.25), int(Hs * 0.4)))
    st = Image.new("RGBA", (Ws, Hs), (0, 0, 0, 0))
    ds = ImageDraw.Draw(st)
    for k, y in enumerate((0.62, 0.78)):
        ds.rounded_rectangle([Ws * 0.2, Hs * y, Ws * 0.8, Hs * (y + 0.07)], radius=Hs * 0.03, fill=(38, 28, 22, 245))
    out.alpha_composite(bl)
    out.alpha_composite(_clipto(st, bl))
    dr = ImageDraw.Draw(out)
    # antenas
    for sx in (-1, 1):
        dr.line([(Ws * (0.5 + sx * 0.07), Hs * 0.2), (Ws * (0.5 + sx * 0.14), Hs * 0.07)], fill=(40, 30, 24, 255), width=lw)
        dr.ellipse([Ws * (0.5 + sx * 0.14) - Ws * 0.025, Hs * 0.07 - Ws * 0.025, Ws * (0.5 + sx * 0.14) + Ws * 0.025, Hs * 0.07 + Ws * 0.025], fill=(40, 30, 24, 255))
    # cabeza
    hd = int(Ws * 0.44)
    head = sphere(int(hd / S), yel, spec=0.5, dark=0.6).resize((hd, hd), Image.LANCZOS)
    out.alpha_composite(head, (int(Ws * 0.28), int(Hs * 0.16)))
    dr = ImageDraw.Draw(out)
    for sx in (-1, 1):
        ex, ey = Ws * (0.5 + sx * 0.085), Hs * 0.35
        dr.ellipse([ex - Ws * 0.055, ey - Ws * 0.06, ex + Ws * 0.055, ey + Ws * 0.06], fill=(30, 22, 20, 255))
        dr.ellipse([ex - Ws * 0.03, ey - Ws * 0.04, ex, ey - Ws * 0.01], fill=(255, 255, 255, 255))
        dr.ellipse([ex - Ws * 0.1 if sx < 0 else ex + Ws * 0.03, ey + Ws * 0.03, ex - Ws * 0.03 if sx < 0 else ex + Ws * 0.1, ey + Ws * 0.08], fill=(255, 140, 140, 140))
    dr.arc([Ws * 0.45, Hs * 0.38, Ws * 0.55, Hs * 0.47], 15, 165, fill=(60, 30, 20, 255), width=lw)
    return _fin(out, W, H)


def a_panal(w, p):
    """Panal de hexágonos con miel. tapados 0-1: fracción de celdas selladas con cera."""
    W = H = int(w)
    S = SS
    Ws, Hs = W * S, H * S
    tap = _clamp01(p.get("tapados", 0.35))
    out = Image.new("RGBA", (Ws, Hs), (0, 0, 0, 0))
    dr = ImageDraw.Draw(out)
    r = Ws / (math.sqrt(3) * 4.6)
    rnd = random.Random(5)
    lw = max(2, int(S * 2.4))
    for row in range(6):
        for col in range(5):
            cx = r * math.sqrt(3) * (col + 0.75 + (0.5 if row % 2 else 0))
            cy = r * 1.1 + row * r * 1.5
            if cx > Ws - r * 0.8 or cy > Hs - r * 0.9:
                continue
            pts = [(cx + r * math.cos(math.radians(60 * i + 30)), cy + r * math.sin(math.radians(60 * i + 30))) for i in range(6)]
            inn = [(cx + r * 0.8 * math.cos(math.radians(60 * i + 30)), cy + r * 0.8 * math.sin(math.radians(60 * i + 30))) for i in range(6)]
            dr.polygon(pts, fill=(176, 108, 22, 255))
            if rnd.random() < tap:
                dr.polygon(inn, fill=(246, 216, 140, 255))
                dr.arc([cx - r * 0.5, cy - r * 0.55, cx + r * 0.2, cy + r * 0.05], 200, 290, fill=(255, 245, 205, 230), width=lw)
            else:
                dr.polygon(inn, fill=(255, 176, 30, 255))
                dr.polygon([(cx - r * 0.5, cy - r * 0.15), (cx - r * 0.1, cy - r * 0.55), (cx + r * 0.1, cy - r * 0.4), (cx - r * 0.3, cy + r * 0.05)], fill=(255, 226, 120, 200))
            dr.polygon(pts, outline=(118, 66, 10, 255))
    return _fin(out, W, H)


def a_vasija(w, p):
    """Vasija de barro antigua con franja decorada."""
    W, H = int(w), int(w * 1.15)
    S = SS
    Ws, Hs = W * S, H * S
    col = _c(p.get("color"), (196, 112, 62))
    prof = [(0.27, 0.03), (0.23, 0.1), (0.2, 0.2), (0.32, 0.3), (0.38, 0.45), (0.36, 0.65), (0.27, 0.85), (0.2, 0.97)]
    left = [(Ws * (0.5 - a), Hs * b) for a, b in prof]
    right = [(Ws * (0.5 + a), Hs * b) for a, b in reversed(prof)]
    poly = _sm(left + right, 10)
    m = Image.new("L", (Ws, Hs), 0)
    ImageDraw.Draw(m).polygon(poly, fill=255)
    arr = np.asarray(m, np.float32) / 255
    xs = (np.arange(Ws, dtype=np.float32) - Ws * 0.5) / (Ws * 0.36)
    sh = 1.05 - 0.55 * (np.abs(xs + 0.18) ** 1.6)
    sh = np.clip(sh, 0.35, 1.15)[None, :]
    ys = np.linspace(1.05, 0.8, Hs, dtype=np.float32)[:, None]
    c = np.array(col, np.float32)[None, None, :] * (sh * ys)[..., None]
    img = Image.fromarray(np.dstack([np.clip(c, 0, 255), arr * 255]).astype(np.uint8), "RGBA")
    dr = ImageDraw.Draw(img)
    dk = _shade(col, 0.5) + (255,)
    lw = max(2, int(S * 2.4))
    dr.rounded_rectangle([Ws * 0.22, Hs * 0.0, Ws * 0.78, Hs * 0.055], radius=Ws * 0.03, fill=_shade(col, 0.85) + (255,), outline=dk, width=lw)
    for y in (0.4, 0.58):
        dr.line([Ws * 0.1, Hs * y, Ws * 0.9, Hs * y], fill=dk, width=lw)
    for k in range(9):
        x0 = Ws * (0.17 + k * 0.073)
        dr.polygon([(x0, Hs * 0.58), (x0 + Ws * 0.0365, Hs * 0.41), (x0 + Ws * 0.073, Hs * 0.58)], fill=_shade(col, 0.62) + (255,))
    out = Image.new("RGBA", (Ws, Hs), (0, 0, 0, 0))
    for sx in (-1, 1):                                                         # asas
        dr2 = ImageDraw.Draw(out)
        ax = Ws * (0.5 + sx * 0.25)
        dr2.arc([ax - Ws * 0.14 if sx < 0 else ax - Ws * 0.1, Hs * 0.2, ax + Ws * 0.1 if sx < 0 else ax + Ws * 0.14, Hs * 0.46], 90 if sx < 0 else 270, 270 if sx < 0 else 90, fill=_shade(col, 0.7) + (255,), width=int(Ws * 0.045))
    out.alpha_composite(img)
    hl = Image.new("RGBA", (Ws, Hs), (0, 0, 0, 0))
    ImageDraw.Draw(hl).rounded_rectangle([Ws * 0.3, Hs * 0.34, Ws * 0.35, Hs * 0.62], radius=Ws * 0.025, fill=(255, 235, 205, 110))
    out.alpha_composite(_clipto(hl, img))
    return _fin(out, W, H)


def a_piramide(w, p):
    """Pirámide de piedra arenosa con hiladas de bloques (tamaño de fondo)."""
    W, H = int(w), int(w * 0.62)
    S = SS
    Ws, Hs = W * S, H * S
    col = _c(p.get("color"), (232, 186, 110))
    img = Image.new("RGBA", (Ws, Hs), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    apex = (Ws * 0.5, Hs * 0.04)
    dr.polygon([apex, (Ws * 0.5, Hs * 0.98), (Ws * 0.02, Hs * 0.98)], fill=col + (255,))
    dr.polygon([apex, (Ws * 0.5, Hs * 0.98), (Ws * 0.98, Hs * 0.98)], fill=_shade(col, 0.68) + (255,))
    ln = _shade(col, 0.52) + (200,)
    for k in range(1, 9):
        y = Hs * (0.04 + 0.94 * (k / 9) ** 1.0)
        half = (y - Hs * 0.04) / (Hs * 0.94) * Ws * 0.48
        dr.line([Ws * 0.5 - half, y, Ws * 0.5 + half, y], fill=ln, width=max(1, int(S * 1.3)))
    dr.line([apex, (Ws * 0.5, Hs * 0.98)], fill=_shade(col, 0.5) + (255,), width=max(2, int(S * 1.8)))
    return _fin(img, W, H)


def a_germen(w, p):
    """Microbio verde con carita. value 0-1: deshidratación (se encoge, se arruga, se pone triste y gris)."""
    d = int(w)
    S = SS
    v = _clamp01(p.get("value", 0))
    k = 1.0 - 0.34 * v
    col = _c(p.get("color"), (110, 200, 90))
    mix = np.array(col, np.float32) * (1 - 0.55 * v) + np.array((150, 130, 90), np.float32) * (0.55 * v)
    col = tuple(int(x) for x in mix)
    out = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    bd = max(8, int(d * 0.74 * k))
    body = sphere(bd, col, spec=0.3 * (1 - v) + 0.05, dark=0.5)
    big = _canvas(bd, bd)
    dr = ImageDraw.Draw(big)
    r = bd * S / 2
    if v > 0.05:
        rnd = random.Random(3)
        for _ in range(int(4 + 12 * v)):
            a = rnd.uniform(0, 2 * math.pi)
            r0 = r * rnd.uniform(0.62, 0.98)
            x0, y0 = r + r0 * math.cos(a), r + r0 * math.sin(a)
            dr.arc([x0 - r * 0.28, y0 - r * 0.28, x0 + r * 0.28, y0 + r * 0.28], math.degrees(a) + 100, math.degrees(a) + 220, fill=_shade(col, 0.5) + (int(200 * v),), width=max(2, int(S * 2)))
    # cara
    for sx in (-1, 1):
        x = r + sx * r * 0.34
        if v < 0.7:
            dr.ellipse([x - r * 0.2, r * 0.58, x + r * 0.2, r * 0.98], fill=(255, 255, 255, 255))
            dr.ellipse([x - r * 0.1, r * 0.68 + r * 0.1 * v, x + r * 0.1, r * 0.92 + r * 0.1 * v], fill=(24, 20, 20, 255))
            dr.ellipse([x - r * 0.07, r * 0.7, x - r * 0.01, r * 0.78], fill=(255, 255, 255, 255))
        else:
            dr.line([x - r * 0.14, r * 0.68, x + r * 0.14, r * 0.92], fill=(24, 20, 20, 255), width=max(3, int(S * 3)))
            dr.line([x - r * 0.14, r * 0.92, x + r * 0.14, r * 0.68], fill=(24, 20, 20, 255), width=max(3, int(S * 3)))
    if v < 0.3:
        dr.arc([r * 0.6, r * 1.1, r * 1.4, r * 1.55], 15, 165, fill=(24, 20, 20, 255), width=max(3, int(S * 2.6)))
    elif v < 0.7:
        dr.line([r * 0.7, r * 1.35, r * 1.3, r * 1.35], fill=(24, 20, 20, 255), width=max(3, int(S * 2.6)))
    else:
        dr.arc([r * 0.6, r * 1.3, r * 1.4, r * 1.75], 195, 345, fill=(24, 20, 20, 255), width=max(3, int(S * 2.6)))
    body.alpha_composite(_fin(big, bd, bd))
    out.alpha_composite(body, ((d - bd) // 2, (d - bd) // 2))
    return out


ASSETS = {
    "frasco": (a_frasco, 1.25, "Frasco de miel con tapa y etiqueta de panal", "nivel (0-1), cristal (0-1), burbujas (0-1: fermenta), tapa: true|false, color (tapa)"),
    "abeja": (a_abeja, 0.95, "Abeja simpática de frente con alas", "color"),
    "panal": (a_panal, 1.0, "Panal de hexágonos con miel", "tapados (0-1)"),
    "vasija": (a_vasija, 1.15, "Vasija de barro antigua con franja decorada", "color"),
    "piramide": (a_piramide, 0.62, "Pirámide de piedra arenosa", "color"),
    "germen": (a_germen, 1.0, "Microbio verde con carita; value 0-1 = deshidratación (se encoge y se arruga)", "value (0-1), color"),
    "esfera": (a_esfera, 1.0, "Bola con carita (personaje base)", "color, mood: neutral|happy|angry|sad|scared|none"),
    "villano": (a_villano, 1.0, "Bolita azul enmascarada con capa y brazos", "color, cape"),
    "bacteria_mala": (a_bacteria_mala, 1.0, "Bacteria morada con picos y cara de enojo", "color, mood"),
    "bacteria_buena": (a_bacteria_buena, 0.38, "Bacilo amarillo sonriente", "color"),
    "burbuja": (a_burbuja, 1.0, "Burbuja translúcida", "color"),
    "persona": (a_persona, 1.15, "(mood yawn + value 0-1 = bostezo animable) Persona de busto con volumen (cada copia con var distinto cambia piel, peinado y ropa)", "skin, hair, shirt, var, style: corto|largo|rizado|moño|calvo|flequillo|gorro, mood: happy|neutral"),
    "medidor": (a_medidor, 0.66, "Medidor semicircular tipo pH", "value (0-14), label"),
    "puerta": (a_puerta, 1.6, "Puerta de madera", "color"),
    "cartel": (a_cartel, 0.78, "Cartel colgante rojo con texto", "text, color"),
    "etiqueta": (a_etiqueta, 0.4, "Caja roja con texto grande para datos (28 años, 300 km)", "text, color, fg"),
    "texto": (a_texto, 0.3, "Texto con contorno", "text, color, size, stroke, fit (true = una sola línea, ajusta el tamaño)"),
    "banda": (a_banda, 0.3, "Rótulo ancho de local", "text, color"),
    "pastilla": (a_pastilla, 0.42, "Pastilla roja y blanca", ""),
    "pez": (a_pez, 0.5, "Pescado plateado", "color"),
    "gato": (a_gato, 1.15, "Gato naranja sentado (mood scared: pelo erizado, bufido)", "color, mood: scared|normal"),
    "hielo": (a_hielo, 0.3, "Cama de hielo (poner al borde inferior)", ""),
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
    "piel": (a_piel, 1.1, "Corte de piel con pelo, folículo, músculo erector y nervio. value 0 (relajada) → 1 (piel de gallina): el pelo se levanta y sale el bultito", "value (0-1); anima con value_from/value_to y value_step 0.02"),
    "pulmones": (a_pulmones, 0.95, "Pulmones con tráquea y bronquios", "value (0-1 inflado), color"),
    "aire": (a_aire, 0.5, "Corrientes de aire (viento) con remolinos", "color"),
    "perro": (a_perro, 1.1, "Perro sentado de frente", "color, mood: normal|yawn"),
    "bebe": (a_bebe, 1.0, "Bebé en burbuja de útero; value = apertura del bostezo", "value (0-1), skin"),
    "peludo": (a_peludo, 1.0, "Ancestro peludo: busto de homínido con pelaje, ceja marcada y cara clara", "erizado (0-1, pelo de punta), mood: neutral|happy|angry|sad|scared, color"),
    "termometro": (a_termometro, 2.3, "Termómetro vertical de azul (frío) a rojo (calor)", "value (0-1)"),
    "audifonos": (a_audifonos, 0.98, "Audífonos de diadema", "color"),
    "nota": (a_nota, 1.3, "Nota musical brillante", "color, double (true = dos notas unidas)"),
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
