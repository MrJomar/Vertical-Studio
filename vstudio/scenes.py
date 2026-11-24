"""Tipos de escena: título, top (ranking), mapa, B-roll con voz y clip de video."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from . import audio as A
from . import geo
from . import tiles as T
from .core import (IMAGE_EXT, VIDEO_EXT, clamp, dim, ease, ffmpeg_bin, fit_text_layer, get_font, hash_key, lerp,
                   mix_color, paste_layer, probe_duration, probe_video, run_quiet, seg, shade_overlay, text_layer,
                   CACHE_DIR, parse_color)
from .media import Background, CaptionTrack, VideoReader


_AVATARS: dict = {}


def parse_time(v, default: float = 0.0) -> float:
    if v is None or v == "":
        return default
    if isinstance(v, (int, float)):
        return float(v)
    parts = str(v).strip().split(":")
    try:
        sec = 0.0
        for p in parts:
            sec = sec * 60 + float(p)
        return sec
    except ValueError:
        return default


def media_list(spec: dict, ctx) -> list:
    out = []
    m = spec.get("media") or []
    if isinstance(m, str):
        m = [x.strip() for x in m.replace(";", "\n").splitlines() if x.strip()]
    out.extend(m)
    d = ctx.resolve(spec.get("media_dir"))
    if d and os.path.isdir(d):
        out.extend(sorted(str(p) for p in Path(d).iterdir() if p.suffix.lower() in (IMAGE_EXT | VIDEO_EXT)))
    return out


# =========================================================================== base
class Scene:
    type = "base"

    def __init__(self, spec: dict, ctx, index: int = 0):
        self.spec, self.ctx, self.index = spec, ctx, index
        self.duration = float(spec.get("duration") or 4.0)
        self.audio: str | None = None
        self.audio_vol = float(spec.get("volume", 1.0))
        self.words: list = []
        self.captions: CaptionTrack | None = None
        self.bg: Background | None = None
        self.transition = spec.get("transition") or ctx.settings.get("transition", "fade")
        self.warnings: list[str] = []

    # ---- preparación (voz, duración) ------------------------------------
    def prepare(self) -> None:
        self._prepare_audio()
        self.prepare_visual()
        if self.words and self.spec.get("captions", True):
            self.captions = CaptionTrack(self.words, self.ctx)

    def _prepare_audio(self) -> None:
        s, ctx = self.spec, self.ctx
        narr = (s.get("narration") or "").strip()
        min_dur = float(s.get("duration") or 0)
        adur = 0.0
        user_audio = ctx.resolve(s.get("audio"))
        if user_audio and os.path.isfile(user_audio):
            self.audio, adur = user_audio, probe_duration(user_audio)
            if s.get("words"):
                self.words = [tuple(w) for w in s["words"]]
            elif narr:
                self.words = []
                if s.get("align") == "whisper" and A.whisper_available():
                    try:
                        segs = A.transcribe(user_audio, ctx.settings.get("whisper_model", "small"))
                        self.words = [w for sg in segs for w in sg["words"]]
                    except Exception as e:
                        self.warnings.append(f"Whisper falló, uso tiempos estimados: {e}")
                if not self.words:
                    self.words = A.estimate_words(narr, adur)
        elif narr and getattr(ctx, "master", {}).get(self.index):
            self.audio, self.words, adur = ctx.master[self.index]
            self._master = True
        elif narr:
            st = ctx.settings
            from . import voices as V
            vz = V.resolve(s, st, self.type, warn=lambda m: m not in self.warnings and self.warnings.append(m))
            self.audio, self.words, adur = A.synthesize(
                narr, vz["engine"], vz["voice"] or A.DEFAULT_VOICE_ES, vz["rate"], vz["model"], vz["style"])
        if adur > 0:
            pad = 0.0 if getattr(self, "_master", False) else float(ctx.settings.get("scene_pad", 0.5))
            self.duration = max(min_dur, adur + pad)
        else:
            self.duration = min_dur or self.default_duration()

    def default_duration(self) -> float:
        return 4.0

    def prepare_visual(self) -> None:
        pass

    def _cue(self, v, default=None):
        """Segundo en que se dice una palabra de la narración (o el número tal cual)."""
        import re as _re
        import unicodedata as _ud
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
        m = _re.match(r"^(.*)#(\d+)$", txt)
        if m:
            txt, nth = m.group(1), int(m.group(2))

        def nm(x):
            x = _ud.normalize("NFD", str(x).lower())
            return _re.sub(r"[^a-z0-9]+", "", "".join(c for c in x if _ud.category(c) != "Mn"))
        seen = 0
        for w in self.words:
            if nm(w[0]) == nm(txt):
                seen += 1
                if seen == nth:
                    return float(w[1])
        self.warnings.append(f"No encontré la palabra «{txt}» en la narración para sincronizar.")
        return default

    # ---- render ----------------------------------------------------------
    def draw(self, t: float) -> Image.Image:  # pragma: no cover
        raise NotImplementedError

    def frame(self, t: float) -> Image.Image:
        img = self.draw(min(max(t, 0.0), self.duration))
        if self.captions:
            self.captions.draw(img, t)
        self._watermark(img)
        return img

    def _watermark(self, img: Image.Image) -> None:
        wm = self.ctx.settings.get("watermark")
        if wm:
            lay = text_layer(wm, "bold", 38, fill=self.ctx.theme["text"], stroke=3, max_w=int(self.ctx.w * 0.8))
            paste_layer(img, lay, self.ctx.w / 2, self.ctx.h * 0.955, alpha=0.7)

    def sfx_events(self) -> list:
        """Eventos de sonido automáticos (t_en_escena, etiqueta). Las subclases lo sobrescriben."""
        return []

    def close(self) -> None:
        if self.bg:
            self.bg.close()


# =========================================================================== título
class TitleScene(Scene):
    type = "title"

    def default_duration(self) -> float:
        return 3.5

    def prepare_visual(self) -> None:
        s = self.spec
        self.bg = Background(self.ctx, media_list(s, self.ctx), self.duration, fit=s.get("fit", "cover"),
                             dim_amount=0.45, seed=self.index)
        self.shade = shade_overlay(self.ctx.w, self.ctx.h, 0.3, 0.5)
        self.has_media = bool(self.bg.items)

    def draw(self, t: float) -> Image.Image:
        c, th = self.ctx, self.ctx.theme
        W, H = c.w, c.h
        img = self.bg.frame(t).copy()
        if self.has_media:
            img.paste(self.shade, (0, 0), self.shade)
        s = self.spec
        accent = parse_color(s.get("color"), th["accent"])
        title = fit_text_layer(s.get("title", ""), "display", 150, 70, int(W * 0.88), int(H * 0.30),
                               fill=th["text"], stroke=9, shadow=8, upper=bool(s.get("upper", True)), spacing=0.02)
        p = seg(t, 0.15, 0.85, "out_back")
        paste_layer(img, title, W / 2, H * 0.44 + (1 - p) * 60, scale=0.85 + 0.15 * p, alpha=clamp(p * 1.6))
        if s.get("kicker"):
            k = text_layer(s["kicker"], "bold", 54, fill=accent, stroke=5, max_w=int(W * 0.85), upper=True)
            paste_layer(img, k, W / 2, H * 0.44 - title.height / 2 - 70, alpha=seg(t, 0.0, 0.5))
        bar = seg(t, 0.35, 1.0, "out_expo")
        d = ImageDraw.Draw(img)
        bw = int(W * 0.42 * bar)
        by = int(H * 0.44 + title.height / 2 + 36)
        d.rounded_rectangle((W / 2 - bw / 2, by, W / 2 + bw / 2, by + 12), 6, fill=accent)
        if s.get("subtitle"):
            sub = fit_text_layer(s["subtitle"], "regular", 62, 38, int(W * 0.8), int(H * 0.16),
                                 fill=th["sub"], stroke=3)
            q = seg(t, 0.6, 1.2)
            paste_layer(img, sub, W / 2, by + 50 + (1 - q) * 30, alpha=q, anchor="top")
        return img


# =========================================================================== top
class TopItemScene(Scene):
    type = "top_item"
    top_index = 0

    def default_duration(self) -> float:
        return 5.0

    def prepare_visual(self) -> None:
        s = self.spec
        self.bg = Background(self.ctx, media_list(s, self.ctx), self.duration, fit=s.get("fit", "cover"),
                             dim_amount=float(s.get("dim", 0.42)), seed=self.index)
        self.shade = shade_overlay(self.ctx.w, self.ctx.h, 0.55, 0.8)

    def draw(self, t: float) -> Image.Image:
        c, th, s = self.ctx, self.ctx.theme, self.spec
        W, H = c.w, c.h
        img = self.bg.frame(t).copy()
        img.paste(self.shade, (0, 0), self.shade)
        accent = parse_color(s.get("color"), th["accent"])
        d = ImageDraw.Draw(img)
        # progreso (pips)
        n = c.top_total
        if n > 1:
            gap, total_w = 10, int(W * 0.84)
            pw = (total_w - gap * (n - 1)) / n
            x0 = (W - total_w) / 2
            for i in range(n):
                col = accent if i == self.top_index else (th["text"] if i < self.top_index else (90, 90, 96))
                d.rounded_rectangle((x0 + i * (pw + gap), H * 0.045, x0 + i * (pw + gap) + pw, H * 0.045 + 10), 5,
                                    fill=col)
        # número
        rank = str(s.get("rank", "")).strip()
        if rank:
            size = 560 if len(rank) <= 2 else 380
            num = text_layer(rank, "display", size, fill=accent, stroke=18, stroke_fill=(0, 0, 0), max_w=W,
                             shadow=12, spacing=0)
            p = seg(t, 0.0, 0.6, "out_back")
            breathe = 1 + 0.012 * math.sin(t * 2.2)
            paste_layer(img, num, W / 2, H * 0.215, scale=(0.3 + 0.7 * p) * breathe, alpha=clamp(p * 2))
            if s.get("kicker"):
                k = text_layer(s["kicker"], "bold", 50, fill=th["text"], stroke=5, max_w=int(W * 0.85), upper=True)
                paste_layer(img, k, W / 2, H * 0.058 + 56, alpha=seg(t, 0.1, 0.5))
        # título
        title_bottom = H * 0.40
        if s.get("title"):
            tl = fit_text_layer(s["title"], "bold", 104, 54, int(W * 0.9), int(H * 0.16), fill=th["text"],
                                stroke=8, shadow=7, upper=bool(s.get("upper", True)), spacing=0.04)
            q = seg(t, 0.25, 0.8, "out_cubic")
            paste_layer(img, tl, W / 2, H * 0.40 + (1 - q) * 70, alpha=clamp(q * 1.5), anchor="top")
            title_bottom = H * 0.40 + tl.height
            bw = int(W * 0.30 * seg(t, 0.5, 1.1, "out_expo"))
            by = int(title_bottom + 14)
            d.rounded_rectangle((W / 2 - bw / 2, by, W / 2 + bw / 2, by + 10), 5, fill=accent)
            title_bottom = by + 24
        if s.get("text"):
            budget = int(H * (0.77 if c.settings.get("caption_y", 0.8) >= 0.77 else 0.70) - title_bottom)
            tx = fit_text_layer(s["text"], "regular", 56, 34, int(W * 0.84), max(budget, 200), fill=th["sub"],
                                stroke=4, shadow=4)
            q = seg(t, 0.7, 1.3)
            paste_layer(img, tx, W / 2, title_bottom + 10 + (1 - q) * 30, alpha=q, anchor="top")
        return img


# =========================================================================== B-roll
class BRollScene(Scene):
    type = "broll"

    def default_duration(self) -> float:
        return 6.0

    def prepare_visual(self) -> None:
        s = self.spec
        self.bg = Background(self.ctx, media_list(s, self.ctx), self.duration, fit=s.get("fit", "cover"),
                             dim_amount=float(s.get("dim", 0.18)), seed=self.index)
        self.shade = shade_overlay(self.ctx.w, self.ctx.h, 0.35, 0.55)

    def draw(self, t: float) -> Image.Image:
        c, th, s = self.ctx, self.ctx.theme, self.spec
        img = self.bg.frame(t).copy()
        img.paste(self.shade, (0, 0), self.shade)
        if s.get("title"):
            lay = fit_text_layer(s["title"], "display", 96, 52, int(c.w * 0.88), int(c.h * 0.14), fill=th["text"],
                                 stroke=7, shadow=6, upper=True, spacing=0.02)
            q = seg(t, 0.1, 0.6, "out_back")
            hold = float(s.get("title_seconds", 0) or 0)
            a = clamp(q * 1.5) * (1.0 if hold <= 0 else 1 - seg(t, hold - 0.4, hold, "linear"))
            paste_layer(img, lay, c.w / 2, c.h * 0.10 + (1 - q) * 40, alpha=a, anchor="top")
        return img


# =========================================================================== clip
class _FaceReader:
    """Lee un video horizontal y recorta 9:16 siguiendo el rostro más grande."""

    def __init__(self, path, start, duration, w, h, fps):
        info = probe_video(path)
        self.W, self.H = w, h
        sh = min(info["h"], 1080) // 2 * 2
        sw = int(round(info["w"] * sh / info["h"] / 2)) * 2
        self.sw, self.sh = sw, sh
        self.reader = VideoReader(path, sw, sh, fps, start, duration, loop=False,
                                  vf=f"fps={fps},scale={sw}:{sh}")
        self.cw = min(sw, int(sh * w / h) // 2 * 2)
        self.cx = sw / 2
        self.tx = sw / 2
        self.det = None
        try:
            xml = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
            if os.path.isfile(xml):
                self.det = cv2.CascadeClassifier(xml)
                if self.det.empty():
                    self.det = None
        except Exception:
            self.det = None
        self.i = -1
        self.last = None

    def frame_at(self, index: int) -> Image.Image:
        while self.i < index:
            arr = self.reader.read_np()
            if arr is None:
                break
            self.i += 1
            if self.det is not None and self.i % 5 == 0:
                g = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
                k = 320.0 / g.shape[1]
                g = cv2.resize(g, (320, int(g.shape[0] * k)))
                faces = self.det.detectMultiScale(g, 1.2, 5, minSize=(24, 24))
                if len(faces):
                    x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                    self.tx = (x + fw / 2) / k
            self.cx += (self.tx - self.cx) * 0.12
            x0 = int(clamp(self.cx - self.cw / 2, 0, self.sw - self.cw))
            crop = arr[:, x0:x0 + self.cw]
            out = cv2.resize(crop, (self.W, self.H), interpolation=cv2.INTER_CUBIC)
            self.last = Image.fromarray(out, "RGB")
        return self.last or Image.new("RGB", (self.W, self.H))

    def close(self):
        self.reader.close()


class ClipScene(Scene):
    type = "clip"

    def default_duration(self) -> float:
        return 30.0

    def _prepare_audio(self) -> None:
        s, ctx = self.spec, self.ctx
        self.src = ctx.resolve(s.get("source"))
        if not self.src or not os.path.isfile(self.src):
            raise FileNotFoundError(f"Clip: no encuentro el video fuente '{s.get('source')}'")
        info = probe_video(self.src)
        self.t0 = parse_time(s.get("start"), 0.0)
        end = parse_time(s.get("end"), 0.0) or (self.t0 + 30)
        if info["duration"]:
            end = min(end, info["duration"])
        self.t1 = max(end, self.t0 + 1.0)
        self.duration = self.t1 - self.t0
        self.words = []
        from .core import has_audio
        if has_audio(self.src):
            wav = CACHE_DIR / "clips" / (hash_key(self.src, self.t0, self.t1, os.path.getmtime(self.src)) + ".wav")
            wav.parent.mkdir(parents=True, exist_ok=True)
            if not wav.exists():
                run_quiet([ffmpeg_bin(), "-y", "-v", "error", "-ss", f"{self.t0:.3f}", "-t", f"{self.duration:.3f}",
                           "-i", self.src, "-vn", "-ac", "2", "-ar", "44100", str(wav)])
            self.audio = str(wav)
        if s.get("words"):
            self.words = [tuple(w) for w in s["words"]]
        elif s.get("captions", True) and self.audio:
            if A.whisper_available():
                try:
                    segs = A.transcribe(self.src, ctx.settings.get("whisper_model", "small"),
                                        s.get("language") or ctx.settings.get("language") or None, self.t0, self.t1)
                    self.words = [w for sg in segs for w in sg["words"]]
                except Exception as e:  # sin modelo descargado / sin internet la primera vez
                    self.warnings.append(f"No se pudieron generar subtítulos del clip: {e}")
            else:
                self.warnings.append("faster-whisper no está instalado: el clip sale sin subtítulos.")

    def prepare_visual(self) -> None:
        self.fit = self.spec.get("fit", "blur")
        self.reader = None
        self.shade = shade_overlay(self.ctx.w, self.ctx.h, 0.35, 0.5)
        self.info = probe_video(self.src)

    def _open(self):
        c = self.ctx
        vertical = self.info["w"] / max(self.info["h"], 1) <= (c.w / c.h) * 1.05
        fit = "cover" if vertical else self.fit
        if fit == "face" and not vertical:
            self.reader = _FaceReader(self.src, self.t0, self.duration, c.w, c.h, c.fps)
        else:
            self.reader = VideoReader(self.src, c.w, c.h, c.fps, self.t0, self.duration, fit=fit, loop=False)

    def draw(self, t: float) -> Image.Image:
        c, th, s = self.ctx, self.ctx.theme, self.spec
        if c.preview:
            from .media import grab_frame
            img = grab_frame(self.src, self.t0 + t, c.w, c.h, "blur" if self.fit != "cover" else "cover")
        else:
            if self.reader is None:
                self._open()
            img = self.reader.frame_at(int(round(t * c.fps))).copy()
        img.paste(self.shade, (0, 0), self.shade)
        hook = s.get("hook")
        if hook:
            hs = float(s.get("hook_seconds", 3.0))
            a = 1.0 if hs <= 0 else 1 - seg(t, hs - 0.4, hs, "linear")
            q = seg(t, 0.05, 0.5, "out_back")
            lay = fit_text_layer(hook, "display", 92, 50, int(c.w * 0.88), int(c.h * 0.16), fill=th["text"],
                                 stroke=7, shadow=6, upper=True, spacing=0.02)
            paste_layer(img, lay, c.w / 2, c.h * 0.085 + (1 - q) * 40, alpha=clamp(q * 1.5) * a, anchor="top")
        return img

    def close(self) -> None:
        if self.reader:
            self.reader.close()
            self.reader = None


# =========================================================================== mapa
def _travel(a, b, p):
    dist = math.hypot(b[0] - a[0], b[1] - a[1])
    big = max(a[2], b[2])
    bump = min(1.1, dist / big * 0.55)
    ls = lerp(math.log(a[2]), math.log(b[2]), p) + bump * math.sin(math.pi * p)
    return (lerp(a[0], b[0], p), lerp(a[1], b[1], p), math.exp(ls))


def vsprite_label(text: str, w: int):
    from .vector import sprite as _sp
    return _sp("etiqueta", w, {"text": text})


class MapScene(Scene):
    type = "map"

    def default_duration(self) -> float:
        return 8.0

    # ---- datos -----------------------------------------------------------
    def prepare_visual(self) -> None:
        c, s = self.ctx, self.spec
        names = s.get("highlight") or []
        if isinstance(names, str):
            names = [n.strip() for n in names.replace(";", ",").replace("\n", ",").split(",") if n.strip()]
        self.hl: list[geo.Feature] = []
        self.hl_labels: dict[str, str] = {}
        self.hl_colors: dict[str, tuple] = {}
        for n in names:
            own = None
            if ":" in n:
                n, _, cc = n.partition(":")
                own = tuple(parse_color(cc.strip(), None) or ()) or None
                n = n.strip()
            f = geo.find_country(n)
            if f is None:
                self.warnings.append(f"Mapa: no reconozco el país '{n}'.")
            else:
                self.hl.append(f)
                self.hl_labels[f.name] = n.strip()
                if own:
                    self.hl_colors[f.name] = own
        self.custom: list[geo.Feature] = []
        gj = c.resolve(s.get("geojson"))
        if gj and os.path.isfile(gj):
            self.custom = geo.load_geojson(gj, s.get("name_key"))
            order = s.get("custom_order")  # opcional: lista de nombres para el orden de aparición
            if order:
                rank = {geo.norm(n): i for i, n in enumerate(order)}
                self.custom.sort(key=lambda f: rank.get(geo.norm(f.name), 999))
        self.places = []
        places = s.get("places") or []
        if isinstance(places, str):
            parsed = []
            for line in places.splitlines():
                line = line.strip()
                if not line:
                    continue
                if "|" in line:
                    parts = [x.strip() for x in line.split("|")]
                    nm, coords = parts[0], parts[1]
                    photo = parts[2] if len(parts) > 2 else ""
                    try:
                        la, lo = [float(v) for v in coords.replace(";", ",").split(",")[:2]]
                        parsed.append({"name": nm, "lat": la, "lon": lo, "photo": photo})
                        continue
                    except ValueError:
                        line = nm
                parsed.append({"name": line})
            places = parsed
        for p in places:
            if isinstance(p, str):
                p = {"name": p}
            lat, lon = p.get("lat"), p.get("lon")
            if lat in (None, "") or lon in (None, ""):
                lat, lon = geo.geocode(p.get("query") or p["name"])
            x, y = geo.to_world(float(lon), float(lat))
            self.places.append({"label": p.get("label", p.get("name", "")), "xy": (float(x), float(y)),
                                "photo": c.resolve(p.get("photo")) if p.get("photo") else ""})
        self.mode = s.get("mode") or ("route" if len(self.places) > 1 and not self.hl else "zoom")
        self._plan()
        self._prep_overlays()
        for i, pl in enumerate(self.places):  # fotos de los lugares → pines con avatar
            if pl.get("photo"):
                t0 = (self.r0 + (self.r1 - self.r0) * self._inv(self.pin_frac[i]) if i else 0.2) if self.route_pts is not None \
                    else (self.pin_t[i] if i < len(self.pin_t) else 0.5)
                self.overlays.append({"photo": pl["photo"], "xy": pl["xy"], "t0": t0 + 0.1, "t1": None, "w": 0.16, "shape": "hexagono", "anim": "float"})

    # ---- overlays (íconos, cifras, fotos sobre el mapa) -------------------
    def _prep_overlays(self) -> None:
        ov = self.spec.get("overlays") or []
        if isinstance(ov, str):
            try:
                ov = json.loads(ov) if ov.strip() else []
            except ValueError as e:
                self.warnings.append(f"Overlays: JSON no válido ({e})")
                ov = []
        self.overlays = []
        by_name = {geo.norm(pl["label"]): pl for pl in self.places}
        for o in ov:
            if not isinstance(o, dict):
                continue
            d = dict(o)
            if d.get("lat") not in (None, "") and d.get("lon") not in (None, ""):
                d["xy"] = geo.to_world(float(d["lon"]), float(d["lat"]))
            elif d.get("place") and geo.norm(d["place"]) in by_name:
                d["xy"] = by_name[geo.norm(d["place"])]["xy"]
            else:
                self.warnings.append(f"Overlay sin posición: {d.get('asset') or d.get('photo')}")
                continue
            d["t0"] = self._cue(d.get("at"), 0.5) or 0.0
            d["t1"] = self._cue(d.get("out"), None)
            self.overlays.append(d)

    @staticmethod
    def _avatar(path: str, size: int, shape: str):
        key = (path, size, shape)
        hit = _AVATARS.get(key)
        if hit is not None:
            return hit
        im = Image.open(path).convert("RGB")
        m = min(im.size)
        im = im.crop(((im.width - m) // 2, (im.height - m) // 2, (im.width + m) // 2, (im.height + m) // 2))
        S = 3
        big = size * S
        im = im.resize((big, big), Image.LANCZOS)
        mask = Image.new("L", (big, big), 0)
        md = ImageDraw.Draw(mask)
        if shape == "hexagono":
            pts = [(big / 2 + big / 2 * math.cos(math.radians(60 * i + 30)), big / 2 + big / 2 * math.sin(math.radians(60 * i + 30))) for i in range(6)]
            md.polygon(pts, fill=255)
        else:
            md.ellipse([0, 0, big - 1, big - 1], fill=255)
        out = Image.new("RGBA", (big + 40 * S // 10, big + 40 * S // 10), (0, 0, 0, 0))
        pad = (out.width - big) // 2
        ring = Image.new("RGBA", (big, big), (255, 255, 255, 255))
        ring.putalpha(mask)
        edge = int(big * 0.05)
        out.alpha_composite(ring, (pad, pad))
        inner = im.resize((big - 2 * edge, big - 2 * edge), Image.LANCZOS)
        im2 = mask.resize((big - 2 * edge, big - 2 * edge), Image.LANCZOS)
        out.paste(inner, (pad + edge, pad + edge), im2)
        out = out.resize((size + size // 6, size + size // 6), Image.LANCZOS)
        if len(_AVATARS) > 60:
            _AVATARS.clear()
        _AVATARS[key] = out
        return out

    def _draw_overlays(self, out: Image.Image, cam, t: float) -> None:
        from .vector import sprite as vsprite
        c = self.ctx
        for o in self.overlays:
            t0, t1 = o["t0"], o["t1"]
            if t < t0 or (t1 is not None and t > t1 + 0.3):
                continue
            pr = seg(t, t0, t0 + 0.45, "out_back")
            al = 1.0 if t1 is None else 1 - seg(t, t1, t1 + 0.3, "linear")
            sx, sy = geo.project(np.array([o["xy"]]), cam, c.w, c.h)[0]
            sx += float(o.get("dx", 0))
            sy += float(o.get("dy", -float(o.get("w", 0.12)) * c.w * 0.65))
            if not (-300 < sx < c.w + 300 and -300 < sy < c.h + 300):
                continue
            wpx = int(float(o.get("w", 0.12)) * c.w)
            if o.get("photo"):
                path = c.resolve(o["photo"])
                if not path or not os.path.isfile(path):
                    continue
                spr = self._avatar(path, wpx, o.get("shape", "circulo"))
            else:
                params = {k: v for k, v in o.items() if k not in ("asset", "lat", "lon", "place", "at", "out", "w", "dx", "dy", "xy", "t0", "t1", "photo", "shape", "anim")}
                spr = vsprite(o["asset"], wpx, params)
            sc = max(0.02, pr)
            if "float" in str(o.get("anim", "")):
                sy += math.sin(t * 2.2) * 8
            spr = spr.resize((max(2, int(spr.width * sc)), max(2, int(spr.height * sc))), Image.BILINEAR)
            if al < 0.99:
                a = spr.getchannel("A").point([int(i * al) for i in range(256)])
                spr = spr.copy()
                spr.putalpha(a)
            out.paste(spr, (int(sx - spr.width / 2), int(sy - spr.height / 2)), spr)

    def _focus_bounds(self):
        bs = [f.bounds for f in self.hl] + [f.full_bounds for f in self.custom]
        bs += [(p["xy"][0], p["xy"][1], p["xy"][0], p["xy"][1]) for p in self.places]
        if not bs:
            return None
        return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))

    def _plan(self) -> None:
        c, s, D = self.ctx, self.spec, self.duration
        W, H = c.w, c.h
        self.pin_t: list[float] = []
        self.hl_t: list[float] = []
        self.custom_t: list[float] = []
        self.route_pts = None
        pz = float(s.get("place_zoom", 0.02))
        fb = self._focus_bounds()
        if fb is None:
            fb = (0.1, 0.25, 0.9, 0.62)
        cxy = ((fb[0] + fb[2]) / 2, (fb[1] + fb[3]) / 2)
        final = (cxy[0], cxy[1], geo.fit_span(fb, W, H, float(s.get("margin", 0.45))))
        if self.mode == "tour" and self.places:
            ov = (cxy[0], cxy[1], geo.fit_span(fb, W, H, 0.5, min_span=pz * 1.5))
            self.kfs = [(0.0, ov, 0.0)]
            hold0 = 0.9
            n = len(self.places)
            per = max(1.0, (D - hold0 - 0.4) / n)
            for i, p in enumerate(self.places):
                td = hold0 + i * per
                ta = td + min(1.6, per * 0.65)
                self.kfs.append((ta, (p["xy"][0], p["xy"][1], pz), td))
                self.pin_t.append(ta - 0.25)
        elif self.mode == "route" and len(self.places) > 1:
            pts = [np.array(p["xy"]) for p in self.places]
            style = s.get("route_style", "arc")
            segs_ = []
            for a, b in zip(pts, pts[1:]):
                arc = geo.bezier_arc(a, b, 0.18 if style == "arc" else 0.0)
                segs_.append(arc if not segs_ else arc[1:])
            self.route_pts = np.vstack(segs_)
            seg_len = np.hypot(*np.diff(self.route_pts, axis=0).T)
            cum = np.concatenate([[0], np.cumsum(seg_len)])
            total = cum[-1] or 1e-9
            self.r0, self.r1 = 1.0, max(2.0, D - 0.9)
            per_seg = len(self.route_pts) // max(1, len(pts) - 1)
            self.pin_frac = [0.0] + [float(cum[min(len(cum) - 1, k * (len(self.route_pts) - 1) // (len(pts) - 1))] / total)
                                     for k in range(1, len(pts))]
            xs, ys = self.route_pts[:, 0], self.route_pts[:, 1]
            rb = (xs.min(), ys.min(), xs.max(), ys.max())
            fit = (float((rb[0] + rb[2]) / 2), float((rb[1] + rb[3]) / 2),
                   geo.fit_span(rb, W, H, float(s.get("margin", 0.5))))
            start = (pts[0][0], pts[0][1], max(fit[2] * 0.55, 0.01))
            self.follow = bool(s.get("follow", len(pts) > 2))
            self.kfs = [(0.0, start, 0.0), (1.4, fit, 0.2)]
            self.fit_cam = fit
        else:  # zoom
            wide = max(final[2] * 5.0, 0.38)
            wide = min(wide, 0.9)
            start = (cxy[0], cxy[1], wide)
            travel = clamp(0.35 * (D - 0.5), 0.8, 2.2)  # zoom rápido y con fuerza
            if final[2] >= wide * 0.9:
                self.kfs = [(0.0, final, 0.0)]
                t_rev = 0.5
            else:
                self.kfs = [(0.0, start, 0.0), (0.5 + travel, final, 0.5)]
                t_rev = 0.5 + travel * 0.6
            items = len(self.hl) + len(self.custom) + len(self.places)
            step = clamp((D - t_rev - 0.6) / max(items, 1), 0.15, 0.7)
            k = 0
            for _ in self.hl:
                self.hl_t.append(t_rev + k * step); k += 1
            for _ in self.custom:
                self.custom_t.append(t_rev + k * step if not s.get("reveal_together") else t_rev); k += 1
            for _ in self.places:
                self.pin_t.append(t_rev + k * step); k += 1
        if self.mode == "tour":
            for _ in self.hl:
                self.hl_t.append(0.4)
            self.custom_t = [0.4] * len(self.custom)
        if self.mode == "route":
            self.hl_t = [0.4] * len(self.hl)
            self.custom_t = [0.4] * len(self.custom)
        self.shade = shade_overlay(self.ctx.w, self.ctx.h, 0.28, 0.4)
        self._setup_tiles()

    # ---- mapa real (teselas) ---------------------------------------------
    def _setup_tiles(self) -> None:
        c, s = self.ctx, self.spec
        style = s.get("style") or c.settings.get("map_style", "satelite")
        self.tiles = None
        self._prefetched = False
        if style == "vectorial":
            return
        custom = c.settings.get("map_tile_url") or None
        if style == "personalizado" and not custom:
            self.warnings.append("Mapa: estilo 'personalizado' sin 'map_tile_url' en ajustes; usé vectorial.")
            return
        if style not in T.PROVIDERS and style != "personalizado":
            style = "satelite"
        self.tiles = T.get_source(style, custom, c.settings.get("map_attribution_text"))
        if c.preview:
            return
        need: set = set()
        D = self.duration
        n = max(2, int(D / 0.125))
        for i in range(n + 1):
            _, ts = self.tiles.tiles_for(self.camera(D * i / n), c.w, c.h)
            need.update(ts)
        report = getattr(c, "report", None)
        if report:
            report("Descargando mapa…", 0.0)
        total, bad = self.tiles.prefetch(sorted(need), progress=(lambda f: report("Descargando mapa…", f)) if report else None)
        self._prefetched = True
        if total and bad / total > 0.35:
            self.warnings.append(f"No pude descargar el mapa real ({bad}/{total} teselas; ¿sin internet?). "
                                 "Usé el estilo vectorial para esta escena.")
            self.tiles = None

    def _ensure_tiles(self, cam) -> None:
        if self._prefetched or self.tiles is None:
            return
        _, ts = self.tiles.tiles_for(cam, self.ctx.w, self.ctx.h)
        total, bad = self.tiles.prefetch(ts)
        if total and bad / total > 0.5:
            self.warnings.append("Vista previa sin internet: se muestra el mapa vectorial.")
            self.tiles = None

    # ---- cámara ----------------------------------------------------------
    def camera(self, t: float):
        cx, cy, span = self._camera_raw(t)
        push = float(self.spec.get("push", 0.07))  # empuje lento continuo (da vida al plano, estilo documental)
        if push and not (self.mode == "route" and getattr(self, "follow", False) and t > 1.4):
            span *= 1.0 - push * clamp(t / max(self.duration, 0.1))
        half_h = span * self.ctx.h / self.ctx.w / 2
        if half_h < 0.5:  # no mostrar el vacío sobre/bajo el mapa si se puede evitar
            cy = min(max(cy, half_h), 1.0 - half_h)
        return (cx, cy, span)

    def _camera_raw(self, t: float):
        if self.mode == "route" and getattr(self, "follow", False) and t > 1.4:
            p = ease("in_out", (t - self.r0) / (self.r1 - self.r0))
            _, tip, _ = geo.polyline_partial(self.route_pts, p)
            span = float(self.spec.get("follow_zoom", self.fit_cam[2] * 0.35))
            q = clamp((t - 1.4) / 1.2)
            q = q * q * (3 - 2 * q)
            f = self.fit_cam
            return _travel(f, (tip[0], tip[1], span), q) if q < 1 else (tip[0], tip[1], span)
        kfs = self.kfs
        for k in range(1, len(kfs)):
            ta, c1, td = kfs[k]
            c0 = kfs[k - 1][1]
            if t < td:
                return c0
            if t < ta:
                return _travel(c0, c1, ease("in_out_cubic", (t - td) / max(ta - td, 1e-6)))
        return kfs[-1][1]

    def sfx_events(self) -> list:
        ev = [(t + 0.05, "pop") for t in self.hl_t] + [(t + 0.05, "click") for t in getattr(self, "pin_t", [])]
        if self.mode == "route":
            ev.append((getattr(self, "r0", 1.0), "whoosh_corto"))
        return ev

    def _base_vector(self, t: float, cam, hlc) -> np.ndarray:
        c, th, s = self.ctx, self.ctx.theme, self.spec
        W, H = c.w, c.h
        img = np.empty((H, W, 3), np.uint8)
        img[:] = th["ocean"]
        if s.get("graticule", True):
            geo.draw_graticule(img, cam, th["grid"])
        feats = geo.load_countries(geo.resolution_for(cam[2]))
        land, border = th["land"], th["border"]
        fills, outl = {}, {}
        for f, t0 in zip(self.hl, self.hl_t):
            p = seg(t, t0, t0 + 0.55, "out_cubic")
            if p > 0:
                fc = self.hl_colors.get(f.name, hlc)
                fills[f.name] = mix_color(land, fc, p)
                outl[f.name] = mix_color(border, tuple(min(255, v + 40) for v in fc), p)
        skip = () if any(f.name == "Antarctica" for f in self.hl) or cam[2] < 0.06 else ("Antarctica",)
        geo.draw_features(img, feats, cam, fills, land, outline=border, line_w=1, skip=skip, outline_map=outl)
        if self.custom:
            cf, co = {}, {}
            base = mix_color(land, hlc, 0.12)
            for f, t0 in zip(self.custom, self.custom_t):
                p = seg(t, t0, t0 + 0.5, "out_cubic")
                cf[f.name] = mix_color(base, hlc, p)
                co[f.name] = mix_color(border, (255, 255, 255), 0.25 + 0.5 * p)
            geo.draw_features(img, self.custom, cam, cf, base, outline=border, line_w=2, outline_map=co)
        return img

    def _grade(self, img: np.ndarray) -> np.ndarray:
        g = self.spec.get("grade") or self.ctx.settings.get("map_grade", "")
        if g not in ("vivo", "cine"):
            return img
        u8 = np.clip(img, 0, 255).astype(np.uint8)
        hsv = cv2.cvtColor(u8, cv2.COLOR_RGB2HSV).astype(np.float32)
        if g == "vivo":
            hsv[..., 1] = np.clip(hsv[..., 1] * 1.32, 0, 255)
            hsv[..., 2] = np.clip(255 * (hsv[..., 2] / 255.0) ** 0.86 * 1.06, 0, 255)
        else:
            hsv[..., 1] = np.clip(hsv[..., 1] * 1.12, 0, 255)
            hsv[..., 2] = np.clip(hsv[..., 2] * 0.92, 0, 255)
        return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB).astype(np.float32)

    def _base_tiles(self, t: float, cam, hlc) -> np.ndarray:
        c, s = self.ctx, self.spec
        W, H = c.w, c.h
        img = self.tiles.render(cam, W, H).astype(np.float32)
        img = self._grade(img)
        layers = []
        if self.hl:
            ha = float(s.get("hl_alpha", 0.8 if self.hl_colors else 0.38))
            layers.append((geo.load_countries(geo.resolution_for(cam[2])),
                           {f.name: seg(t, t0, t0 + 0.55, "out_cubic") for f, t0 in zip(self.hl, self.hl_t)}, ha))
        if self.custom:
            layers.append((self.custom, {f.name: seg(t, t0, t0 + 0.5, "out_cubic")
                                         for f, t0 in zip(self.custom, self.custom_t)}, 0.34))
        union = np.zeros((H, W), np.float32)
        maxp = 0.0
        hl_col = np.array(hlc, np.float32)
        for feats, probs, alpha in layers:
            act = {n: p for n, p in probs.items() if p > 0}
            if not act:
                continue
            mask = np.zeros((H, W), np.uint8)
            geo.draw_features(mask, feats, cam, {n: int(255 * p) for n, p in act.items()}, 0, only=set(act))
            a = mask.astype(np.float32) / 255.0
            if any(n in self.hl_colors for n in act):
                colimg = np.empty((H, W, 3), np.float32)
                colimg[:] = hl_col
                for n in act:
                    if n in self.hl_colors:
                        m1 = np.zeros((H, W), np.uint8)
                        geo.draw_features(m1, feats, cam, {n: 255}, 0, only={n})
                        colimg[m1 > 0] = self.hl_colors[n]
                img = img * (1 - a[..., None] * alpha) + colimg * (a[..., None] * alpha)
            else:
                img = img * (1 - a[..., None] * alpha) + hl_col * (a[..., None] * alpha)
            union = np.maximum(union, a)
            maxp = max(maxp, max(act.values()))
        if union.any() and s.get("dim_outside", True):
            soft = cv2.GaussianBlur(union, (0, 0), 7)
            out_w = (1 - soft)[..., None] * min(1.0, maxp)
            ds = float(s.get("desat_outside", 0.7))  # entorno en grises, país de color (estilo Geo Chris)
            if ds > 0:
                gray = img.mean(axis=2, keepdims=True)
                img = img * (1 - ds * out_w) + gray * (ds * out_w)
            img = img * (1 - 0.45 * out_w)
        out = np.clip(img, 0, 255).astype(np.uint8)
        # contornos con brillo
        for feats, probs, _ in layers:
            act = {n: p for n, p in probs.items() if p > 0}
            if not act:
                continue
            glow = {n: mix_color((0, 0, 0), hlc, min(1.0, p)) for n, p in act.items()}
            white = {n: mix_color((0, 0, 0), (255, 255, 255), min(1.0, p)) for n, p in act.items()}
            geo.draw_features(out, feats, cam, {}, None, outline=None, line_w=7, only=set(act), outline_map=glow)
            geo.draw_features(out, feats, cam, {}, None, outline=None, line_w=2, only=set(act), outline_map=white)
        return out

    # ---- dibujo ----------------------------------------------------------
    def draw(self, t: float) -> Image.Image:
        c, th, s = self.ctx, self.ctx.theme, self.spec
        W, H = c.w, c.h
        cam = self.camera(t)
        hlc = tuple(parse_color(s.get("color"), th["pick"]))
        land, border = th["land"], th["border"]
        self._ensure_tiles(cam)
        if self.tiles is not None:
            img = self._base_tiles(t, cam, hlc)
        else:
            img = self._base_vector(t, cam, hlc)
        # ruta
        marker = None
        if self.route_pts is not None:
            p = ease("in_out", (t - self.r0) / (self.r1 - self.r0))
            part, tip, ang = geo.polyline_partial(self.route_pts, p)
            if len(part) >= 2:
                pp = geo._px16(geo.project(part, cam, W, H))
                rw = int(s.get("route_width", 6))
                rcol = tuple(parse_color(s.get("route_color"), hlc)) if s.get("route_color") else hlc
                glow = mix_color(th["ocean"], rcol, 0.4)
                cv2.polylines(img, [pp], False, glow, rw * 2 + 1, cv2.LINE_AA, 4)
                cv2.polylines(img, [pp], False, (0, 0, 0), rw + 4, cv2.LINE_AA, 4) if s.get("route_outline", False) else None
                cv2.polylines(img, [pp], False, rcol, rw, cv2.LINE_AA, 4)
            marker = (geo.project(np.array([tip]), cam, W, H)[0], ang)
            self._route_p = p
        # pines
        pins = []
        for i, pl in enumerate(self.places):
            if self.route_pts is not None:
                t0 = self.r0 + (self.r1 - self.r0) * self._inv(self.pin_frac[i]) if i else 0.2
            else:
                t0 = self.pin_t[i] if i < len(self.pin_t) else 0.5
            pr = seg(t, t0, t0 + 0.45, "out_back")
            if pr <= 0:
                continue
            sx, sy = geo.project(np.array([pl["xy"]]), cam, W, H)[0]
            if -200 < sx < W + 200 and -200 < sy < H + 200:
                pins.append((pl["label"], float(sx), float(sy), pr, t - t0))
        for _, sx, sy, pr, age in pins:
            ph = (age * 0.8) % 1.0
            rr = lerp(14, 56, ph) * min(1, pr)
            ringc = mix_color(th["ocean"], hlc, 1 - ph)
            cv2.circle(img, (int(sx * 16), int(sy * 16)), int(rr * 16), ringc, 3, cv2.LINE_AA, 4)
            cv2.circle(img, (int(sx * 16), int(sy * 16)), int(18 * pr * 16), (255, 255, 255), -1, cv2.LINE_AA, 4)
            cv2.circle(img, (int(sx * 16), int(sy * 16)), int(12 * pr * 16), hlc, -1, cv2.LINE_AA, 4)
        tip_xy = marker[0] if marker is not None else None
        if marker is not None and s.get("marker", "dot") == "none":
            marker = None
        if marker is not None:
            (mx, my), ang = marker
            if s.get("marker", "dot") == "arrow":
                L = 30
                tri = np.array([[mx + math.cos(ang) * L, my + math.sin(ang) * L],
                                [mx + math.cos(ang + 2.5) * L * 0.8, my + math.sin(ang + 2.5) * L * 0.8],
                                [mx + math.cos(ang - 2.5) * L * 0.8, my + math.sin(ang - 2.5) * L * 0.8]])
                cv2.fillPoly(img, [geo._px16(tri)], (255, 255, 255), cv2.LINE_AA, 4)
            else:
                cv2.circle(img, (int(mx * 16), int(my * 16)), 20 * 16, (255, 255, 255), -1, cv2.LINE_AA, 4)
                cv2.circle(img, (int(mx * 16), int(my * 16)), 13 * 16, hlc, -1, cv2.LINE_AA, 4)
        self._draw_arrows(img, cam, t)
        out = Image.fromarray(img, "RGB")
        if s.get("shade", True):
            out.paste(self.shade, (0, 0), self.shade)
        if self.tiles is not None and self.tiles.attr and c.settings.get("map_attribution", True):
            at = text_layer(self.tiles.attr, "regular", 26, fill=(255, 255, 255), stroke=3, max_w=int(W * 0.85))
            paste_layer(out, at, 18, H * 0.915, alpha=0.75, anchor="left")
        # etiquetas
        if s.get("labels", True):
            for f, t0 in zip(self.hl, self.hl_t):
                p = seg(t, t0 + 0.2, t0 + 0.7)
                if p <= 0:
                    continue
                b = f.bounds
                wpx = (b[2] - b[0]) * W / cam[2]
                if wpx < 140:
                    continue
                sx, sy = geo.project(np.array([f.center]), cam, W, H)[0]
                if 0 < sx < W and 0 < sy < H:
                    lay = text_layer(self.hl_labels.get(f.name, f.name), "bold", int(clamp(wpx * 0.16, 34, 72)),
                                     fill=(255, 255, 255), stroke=6,
                                     max_w=int(W * 0.7), upper=True)
                    paste_layer(out, lay, sx, sy - (1 - p) * 20, alpha=p)
            for f, t0 in zip(self.custom, self.custom_t):
                if not s.get("custom_labels", True):
                    break
                b = f.bounds
                wpx = (b[2] - b[0]) * W / cam[2]
                p = seg(t, t0 + 0.2, t0 + 0.7)
                if p <= 0 or wpx < 90:
                    continue
                sx, sy = geo.project(np.array([f.center]), cam, W, H)[0]
                if 0 < sx < W and 0 < sy < H:
                    lay = text_layer(f.name, "bold", int(clamp(wpx * 0.14, 30, 56)), fill=(255, 255, 255), stroke=5,
                                     max_w=int(wpx * 0.9), upper=False)
                    paste_layer(out, lay, sx, sy, alpha=p)
        self._draw_overlays(out, cam, t)
        if tip_xy is not None and (s.get("tip_photo") or s.get("tip_name")):
            self._draw_tip(out, tip_xy, t)
        self._draw_route_labels(out, cam, t)
        for i_, (label, sx, sy, pr, _) in enumerate(pins):
            if label:
                lay = text_layer(label, "bold", 54, fill=(255, 255, 255), stroke=7, max_w=int(W * 0.6))
                paste_layer(out, lay, sx, sy - 70 - (1 - pr) * 20, alpha=clamp(pr), anchor="bottom")
        out = self._post(out, t)
        if s.get("title"):
            lay = fit_text_layer(s["title"], "display", 110, 56, int(W * 0.88), int(H * 0.16), fill=th["text"],
                                 stroke=8, shadow=7, upper=True, spacing=0.02)
            q = seg(t, 0.1, 0.6, "out_back")
            paste_layer(out, lay, W / 2, H * 0.085 + (1 - q) * 40, alpha=clamp(q * 1.5), anchor="top")
        return out


    # ---- extras de estilo «documental» ------------------------------------
    def _draw_tip(self, out: Image.Image, pos, t: float) -> None:
        """Avatar (foto en hexágono) y nombre pegados a la punta de la ruta."""
        c, s = self.ctx, self.spec
        q = seg(t, self.r0 - 0.1, self.r0 + 0.5, "out_back")
        if q <= 0:
            return
        sx, sy = float(pos[0]), float(pos[1])
        wpx = int(float(s.get("tip_size", 0.15)) * c.w)
        path = c.resolve(s.get("tip_photo")) if s.get("tip_photo") else None
        top = sy
        if path and os.path.isfile(path):
            spr = self._avatar(path, wpx, s.get("tip_shape", "hexagono"))
            spr = spr.resize((max(2, int(spr.width * q)), max(2, int(spr.height * q))), Image.BILINEAR)
            out.paste(spr, (int(sx - spr.width / 2), int(sy + wpx * 0.12 - spr.height / 2)), spr)
            top = sy - spr.height / 2
        if s.get("tip_name"):
            lay = text_layer(s["tip_name"], "bold", 46, fill=(255, 255, 255), stroke=6, max_w=int(c.w * 0.6))
            paste_layer(out, lay, sx, top - 8, alpha=clamp(q), anchor="bottom")

    def _draw_route_labels(self, out: Image.Image, cam, t: float) -> None:
        """Rótulos pegados a la ruta, girados según su dirección («2 años», «300 km»)."""
        if self.route_pts is None:
            return
        rl = self.spec.get("route_labels") or []
        if isinstance(rl, str):
            try:
                rl = json.loads(rl) if rl.strip() else []
            except ValueError:
                rl = []
        c = self.ctx
        for d in rl:
            if not isinstance(d, dict) or not d.get("text"):
                continue
            frac = float(d.get("frac", 0.5))
            t0 = self.r0 + (self.r1 - self.r0) * self._inv(frac)
            q = seg(t, t0, t0 + 0.4, "out_back")
            if q <= 0:
                continue
            _, pt, ang = geo.polyline_partial(self.route_pts, frac)
            sx, sy = geo.project(np.array([pt]), cam, c.w, c.h)[0]
            if not (-200 < sx < c.w + 200 and -200 < sy < c.h + 200):
                continue
            kind = d.get("style", "rotado")
            if kind == "etiqueta":
                lay = vsprite_label(d["text"], int(d.get("size", 0.2) * c.w))
            else:
                lay = text_layer(str(d["text"]), "bold", int(d.get("size", 54)), fill=(255, 255, 255), stroke=7, max_w=int(c.w * 0.7))
                deg = -math.degrees(ang)
                if deg < -90 or deg > 90:
                    deg += 180
                steep = abs(deg) > 62
                lay = lay.rotate(0 if (steep or kind != "rotado") else deg, Image.BICUBIC, expand=True)
            off = float(d.get("offset", 46))
            nx, ny = -math.sin(ang), math.cos(ang)
            if kind != "etiqueta" and steep:
                nx, ny, off = 1.0, 0.0, off + lay.width / 2 * 0.9
            lay = lay.resize((max(2, int(lay.width * q)), max(2, int(lay.height * q))), Image.BILINEAR) if q < 0.99 else lay
            out.paste(lay, (int(sx + nx * off - lay.width / 2), int(sy + ny * off - lay.height / 2)), lay)

    def _draw_arrows(self, img: np.ndarray, cam, t: float) -> None:
        """Flechas punteadas en arco entre dos puntos, con punta y rótulo de destino."""
        ar = self.spec.get("arrows") or []
        if isinstance(ar, str):
            try:
                ar = json.loads(ar) if ar.strip() else []
            except ValueError:
                ar = []
        if not ar:
            return
        c = self.ctx
        by_name = {geo.norm(pl["label"]): pl["xy"] for pl in self.places}
        if not hasattr(self, "_arrow_cache"):
            self._arrow_cache = {}
        for i, d in enumerate(ar):
            if not isinstance(d, dict):
                continue
            key = i
            if key not in self._arrow_cache:
                pts = []
                for k in ("from", "to"):
                    v = d.get(k)
                    if isinstance(v, (list, tuple)) and len(v) == 2:
                        pts.append(geo.to_world(float(v[1]), float(v[0])))
                    elif isinstance(v, str) and geo.norm(v) in by_name:
                        pts.append(by_name[geo.norm(v)])
                    elif isinstance(v, str):
                        la, lo = geo.geocode(v)
                        pts.append(geo.to_world(lo, la))
                if len(pts) != 2:
                    self._arrow_cache[key] = None
                    continue
                self._arrow_cache[key] = (geo.bezier_arc(pts[0], pts[1], float(d.get("bend", 0.16)), 60),
                                          self._cue(d.get("at"), 0.5) or 0.0)
            ent = self._arrow_cache[key]
            if ent is None:
                continue
            arc, t0 = ent
            p = seg(t, t0, t0 + float(d.get("dur", 1.2)), "in_out_cubic")
            if p <= 0:
                continue
            part, tip, ang = geo.polyline_partial(arc, p)
            scr = geo.project(part, cam, c.w, c.h)
            col = tuple(parse_color(d.get("color"), (255, 255, 255)))
            wd = int(d.get("width", 9))
            seglen = np.hypot(*np.diff(scr, axis=0).T)
            cum = np.concatenate([[0], np.cumsum(seglen)])
            on, off = wd * 2.6, wd * 1.7
            pos = 0.0
            if d.get("dash", True):
                while pos < cum[-1]:
                    a0, a1 = pos, min(pos + on, cum[-1])
                    xs = np.interp([a0, a1], cum, scr[:, 0])
                    ys = np.interp([a0, a1], cum, scr[:, 1])
                    cv2.line(img, (int(xs[0]), int(ys[0])), (int(xs[1]), int(ys[1])), (20, 20, 20), wd + 4, cv2.LINE_AA)
                    cv2.line(img, (int(xs[0]), int(ys[0])), (int(xs[1]), int(ys[1])), col, wd, cv2.LINE_AA)
                    pos += on + off
            else:
                cv2.polylines(img, [geo._px16(scr)], False, col, wd, cv2.LINE_AA, 4)
            if len(scr) >= 2:
                tx, ty = scr[-1]
                v = scr[-1] - scr[max(0, len(scr) - 4)]
                a_ = math.atan2(v[1], v[0])
                L = wd * 3.4
                tri = np.array([[tx + math.cos(a_) * L, ty + math.sin(a_) * L],
                                [tx + math.cos(a_ + 2.5) * L * 0.9, ty + math.sin(a_ + 2.5) * L * 0.9],
                                [tx + math.cos(a_ - 2.5) * L * 0.9, ty + math.sin(a_ - 2.5) * L * 0.9]])
                cv2.fillPoly(img, [geo._px16(tri)], col, cv2.LINE_AA, 4)
        self._arrow_labels = [(d, self._arrow_cache.get(i)) for i, d in enumerate(ar) if isinstance(d, dict) and d.get("label")]

    def _post(self, out: Image.Image, t: float) -> Image.Image:
        """Efectos de acabado: inclinación 3D, partículas (nieve…), fundido a blanco/negro, rótulos de flechas."""
        c, s = self.ctx, self.spec
        W, H = c.w, c.h
        cam = self.camera(t)
        for d, ent in getattr(self, "_arrow_labels", []):
            if not ent:
                continue
            arc, t0 = ent
            q = seg(t, t0 + float(d.get("dur", 1.2)) * 0.8, t0 + float(d.get("dur", 1.2)) + 0.3, "out_back")
            if q <= 0:
                continue
            sx, sy = geo.project(arc[-1:].copy(), cam, W, H)[0]
            lay = text_layer(str(d["label"]), "bold", int(d.get("size", 44)), fill=(255, 255, 255), stroke=6, max_w=int(W * 0.5))
            paste_layer(out, lay, sx, sy - 48, alpha=clamp(q), anchor="bottom")
        tilt = float(s.get("tilt", 0) or 0)
        if tilt > 0:
            k = clamp(tilt / 40.0) * ease("in_out_cubic", clamp((t - float(s.get("tilt_start", 0.2))) / 1.6))
            if k > 0.01:
                arr = np.asarray(out)
                inset, top = k * 0.2 * W, k * 0.1 * H
                src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
                dst = np.float32([[inset, top], [W - inset, top], [W, H], [0, H]])
                z = 1 + k * 0.28  # acerca para que no se vea el borde superior
                dst = ((dst - [W / 2, H]) * z + [W / 2, H]).astype(np.float32)
                M = cv2.getPerspectiveTransform(src, dst)
                arr = cv2.warpPerspective(arr, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
                out = Image.fromarray(arr, "RGB")
        fx = s.get("fx") or ""
        names = [x.strip() for x in (fx if isinstance(fx, list) else str(fx).replace("+", ",").split(",")) if x.strip()]
        if names:
            from .vector import _FX, FX_CHOICES
            names = [n for n in names if n in FX_CHOICES]
            if names:
                if not hasattr(self, "_fx"):
                    self._fx = _FX(names, (255, 255, 255), W, H, self.index)
                rgba = out.convert("RGBA")
                self._fx.draw(rgba, t, False)
                self._fx.draw(rgba, t, True)
                out = rgba.convert("RGB")
        intro = s.get("intro") or ""
        if intro in ("blanco", "negro"):
            a = 1 - seg(t, 0.0, float(s.get("intro_dur", 0.7)), "linear")
            if a > 0.01:
                out = Image.blend(out, Image.new("RGB", (W, H), (255, 255, 255) if intro == "blanco" else (0, 0, 0)), a)
        return out

    def _inv(self, frac: float) -> float:
        """Inversa aproximada de ease('in_out') para sincronizar pines con el avance de la ruta."""
        lo, hi = 0.0, 1.0
        for _ in range(20):
            mid = (lo + hi) / 2
            if ease("in_out", mid) < frac:
                lo = mid
            else:
                hi = mid
        return lo


# =========================================================================== catálogo / esquema para la GUI
STYLE_CHOICES = ["cover", "blur"]

SCENE_TYPES: dict[str, dict] = {
    "map": {"label": "Mapa animado", "desc": "Mapa real (satélite, calles…) con zoom a países, tour de lugares o rutas animadas.", "icon": "map", "cls": MapScene, "fields": [
        ("title", "Título", "text", ""), ("mode", "Modo", "choice", "zoom", ["zoom", "tour", "route"]),
        ("style", "Estilo de mapa", "choice", "", [""] + T.STYLE_CHOICES),
        ("highlight", "Países a resaltar (separados por coma)", "text", ""),
        ("places", "Lugares: uno por línea, «Nombre» o «Nombre | lat, lon | foto opcional»", "multiline", ""),
        ("geojson", "GeoJSON propio (barrios, colonias, estados…)", "file", ""),
        ("overlays", "Íconos/cifras/fotos sobre el mapa (JSON)", "json", []),
        ("route_style", "Ruta: estilo", "choice", "arc", ["arc", "line"]),
        ("route_color", "Ruta: color (#rrggbb, p. ej. #f2ff2e)", "text", ""), ("route_width", "Ruta: grosor", "number", 6),
        ("push", "Empuje lento de cámara (0 = off)", "number", 0.07), ("desat_outside", "Entorno en grises (0-1)", "number", 0.7), ("follow", "Ruta: la cámara sigue la punta", "bool", False), ("follow_zoom", "Zoom al seguir (menor = más cerca)", "number", 0.0),
        ("tip_photo", "Avatar en la punta de la ruta (foto)", "file", ""), ("tip_name", "Nombre sobre el avatar", "text", ""),
        ("route_labels", "Rótulos sobre la ruta (JSON: [{\"frac\":0.5,\"text\":\"2 años\"}])", "json", []),
        ("arrows", "Flechas punteadas (JSON: [{\"from\":\"Lima\",\"to\":[53.7,-0.3],\"label\":\"Hull, UK\",\"at\":2}])", "json", []),
        ("tilt", "Inclinación 3D (0-40)", "number", 0), ("grade", "Color del mapa", "choice", "", ["", "vivo", "cine"]),
        ("fx", "Efectos (nieve, polvo_luz, bokeh)", "text", ""), ("intro", "Entrada", "choice", "", ["", "blanco", "negro"]),
        ("place_zoom", "Zoom por lugar (menor = más cerca)", "number", 0.02),
        ("narration", "Narración (voz y subtítulos)", "multiline", ""), ("duration", "Duración mínima (s)", "number", 8.0),
        ("color", "Color de resalte (#rrggbb)", "text", "")]},
    "vector": {"label": "Animación vectorial", "desc": "Personajes, objetos y fondos animados por capas, sincronizados con la voz (estilo explicativo).", "icon": "shapes", "cls": None, "fields": [
        ("narration", "Narración (voz y subtítulos)", "multiline", ""),
        ("bg", "Fondo", "choice", "olas", ["olas", "azulejos", "niebla", "rayos", "cuarto", "cuadricula", "espacio", "musculo", "cuerpo", "degradado", "color"]),
        ("bg_colors", "Colores del fondo (#hex, separados por coma)", "text", ""),
        ("audio", "Audio propio (opcional, en vez de voz IA)", "file", ""),
        ("align", "Sincronía con audio propio", "choice", "estimado", ["estimado", "whisper"]),
        ("layers", "Capas animadas (JSON)", "json", []),
        ("fx", "Efectos ambientales (humo, bokeh, corazones, brillos, nieve, burbujas, polvo_luz)", "text", ""),
        ("camera", "Cámara", "choice", "", ["", "push", "pull", "push_fuerte", "drift", "pan_left", "pan_right"]),
        ("caption_style", "Estilo de subtítulos", "choice", "suave", ["suave", "caja", "clasico"]),
        ("caption_y", "Posición de subtítulos (0 arriba – 1 abajo)", "number", 0.12),
        ("duration", "Duración mínima (s)", "number", 5.0)]},
    "broll": {"label": "B-roll con voz", "desc": "Imágenes y videos con fundidos, narración y subtítulos palabra por palabra.", "icon": "film", "cls": BRollScene, "fields": [
        ("media", "Imágenes/videos", "files", []), ("media_dir", "…o carpeta con medios", "file", ""),
        ("narration", "Narración (voz y subtítulos)", "multiline", ""), ("title", "Título superior (opcional)", "text", ""),
        ("audio", "Audio propio (opcional, en vez de voz IA)", "file", ""),
        ("duration", "Duración mínima (s)", "number", 6.0), ("fit", "Ajuste", "choice", "cover", STYLE_CHOICES)]},
    "clip": {"label": "Clip de video largo", "desc": "Recorta un fragmento de un video largo a vertical con subtítulos y gancho.", "icon": "scissors", "cls": ClipScene, "fields": [
        ("source", "Video fuente", "file", ""), ("start", "Inicio (s o mm:ss)", "text", "0"),
        ("end", "Fin (s o mm:ss)", "text", "30"), ("fit", "Reencuadre", "choice", "blur", ["blur", "cover", "face"]),
        ("hook", "Gancho (texto superior)", "text", ""), ("captions", "Subtítulos automáticos", "bool", True)]},
}


from .vector import VectorScene  # noqa: E402  (registro tardío para evitar importación circular)

SCENE_TYPES["vector"]["cls"] = VectorScene
