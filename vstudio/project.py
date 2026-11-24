"""Proyecto (JSON), contexto de render, transiciones y render completo con audio."""
from __future__ import annotations

import copy
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Callable

from PIL import Image

from .core import CACHE_DIR, Encoder, ease, get_theme, mix_audio, mux, clamp
from .scenes import SCENE_TYPES

DEFAULT_SETTINGS = {
    "width": 1080, "height": 1920, "fps": 30,
    "encoder": "auto", "quality": "alta",
    "theme": "oscuro", "theme_colors": {},
    "tts_engine": "edge", "voice": "es-MX-JorgeNeural", "tts_rate": 0, "scene_pad": 0.5,
    "transition": "fade", "transition_seconds": 0.3,
    "map_style": "satelite", "map_tile_url": "", "map_attribution": True,
    "sfx": "manual", "sfx_volume": 0.5, "music": "", "music_volume": 0.12, "duck_music": True,
    "caption_size": 78, "caption_y": 0.80, "caption_font": "display", "caption_upper": True,
    "watermark": "", "whisper_model": "small", "language": "", "align_voice": "whisper",
}

TRANSITIONS = ["fade", "slide", "zoom", "flash", "wipe", "cut"]


class Cancelled(Exception):
    pass


class Ctx:
    def __init__(self, settings: dict, base_dir: str, preview: bool = False):
        self.settings = {**DEFAULT_SETTINGS, **(settings or {})}
        self.theme = get_theme(self.settings)
        self.w, self.h = int(self.settings["width"]), int(self.settings["height"])
        self.fps = int(self.settings["fps"])
        self.base_dir = base_dir or os.getcwd()
        self.preview = preview
        self.top_total = 0
        self.warnings: list[str] = []
        self.report = lambda msg, frac: None
        self.master: dict = {}

    def resolve(self, p) -> str | None:
        if not p:
            return None
        p = os.path.expanduser(str(p))
        if os.path.isabs(p):
            return p
        for base in (self.base_dir, os.getcwd()):
            c = os.path.join(base, p)
            if os.path.exists(c):
                return c
        return os.path.join(self.base_dir, p)


def apply_transition(prev: Image.Image, cur: Image.Image, p: float, kind: str) -> Image.Image:
    p = ease("in_out", p)
    W, H = cur.size
    if kind == "slide":
        out = Image.new("RGB", (W, H))
        out.paste(prev, (-int(W * p * 0.35), 0))
        out.paste(cur, (int(W * (1 - p)), 0))
        return out
    if kind == "zoom":
        s = 1.28 - 0.28 * p
        w2, h2 = int(W * s), int(H * s)
        big = cur.resize((w2, h2), Image.BILINEAR)
        big = big.crop(((w2 - W) // 2, (h2 - H) // 2, (w2 - W) // 2 + W, (h2 - H) // 2 + H))
        return Image.blend(prev, big, clamp(p * 1.15))
    if kind == "flash":
        white = Image.new("RGB", (W, H), (255, 255, 255))
        return Image.blend(prev, white, p * 2) if p < 0.5 else Image.blend(white, cur, (p - 0.5) * 2)
    if kind == "wipe":
        y = int(H * (1 - p))
        out = prev.copy()
        out.paste(cur.crop((0, y, W, H)), (0, y))
        return out
    return Image.blend(prev, cur, p)  # fade


class Project:
    def __init__(self, data: dict | None = None, path: str | None = None):
        self.data = data or {"settings": {}, "scenes": []}
        self.data.setdefault("settings", {})
        self.data.setdefault("scenes", [])
        self.path = path

    # ---- archivo ---------------------------------------------------------
    @classmethod
    def load(cls, path: str) -> "Project":
        return cls(json.loads(Path(path).read_text("utf-8")), path)

    def save(self, path: str | None = None) -> None:
        self.path = path or self.path
        Path(self.path).write_text(json.dumps(self.data, ensure_ascii=False, indent=2), "utf-8")

    @property
    def settings(self) -> dict:
        return self.data["settings"]

    @property
    def scenes(self) -> list[dict]:
        return self.data["scenes"]

    @property
    def base_dir(self) -> str:
        return os.path.dirname(os.path.abspath(self.path)) if self.path else os.getcwd()

    # ---- construcción ----------------------------------------------------
    def build(self, ctx: Ctx) -> list:
        out = []
        tops = 0
        try:
            from . import audio as _A
            _A.ALIGN_CFG.update({"on": ctx.settings.get("align_voice", "whisper") != "estimado",
                                 "model": ctx.settings.get("whisper_model", "small") or "small",
                                 "lang": (ctx.settings.get("language") or "es")})
            if _A.ALIGN_CFG["on"] and not _A.whisper_available():
                ctx.warnings.append("Subtítulos: instala faster-whisper (pip install faster-whisper) para que sigan la voz real; por ahora van estimados.")
        except Exception:
            pass
        try:
            from . import master
            ctx.master = master.plan(self.scenes, ctx.settings, [x.get("type") for x in self.scenes],
                                     warn=lambda m: m not in ctx.warnings and ctx.warnings.append(m))
        except Exception as e:   # sin voz maestra se usa la voz por escena (y el error real lo da esa llamada)
            ctx.master = {}
            ctx.warnings.append(f"Voz maestra no disponible: {e}")
        for i, spec in enumerate(self.scenes):
            info = SCENE_TYPES.get(spec.get("type"))
            if not info:
                raise ValueError(f"Escena {i + 1}: tipo desconocido '{spec.get('type')}'")
            sc = info["cls"](spec, ctx, i)
            if spec.get("type") == "top_item":
                sc.top_index = tops
                tops += 1
            out.append(sc)
        ctx.top_total = tops
        return out

    def preview_frame(self, scene_index: int, t: float | None = None) -> Image.Image:
        """Un fotograma de la escena (sin red: voz en modo silencio para estimar tiempos)."""
        st = dict(self.settings)
        st["tts_engine"] = "silencio"
        ctx = Ctx(st, self.base_dir, preview=True)
        scenes = self.build(ctx)
        sc = scenes[scene_index]
        sc.prepare()
        try:
            tt = t if t is not None else min(sc.duration * 0.55, 2.5)
            return sc.frame(tt).copy()
        finally:
            sc.close()

    # ---- render ----------------------------------------------------------
    def render(self, out_path: str, progress: Callable[[str, float], None] | None = None,
               cancel: Callable[[], bool] | None = None) -> dict:
        t_start = time.time()
        prog = progress or (lambda s, f: None)
        ctx = Ctx(self.settings, self.base_dir)
        scenes = self.build(ctx)
        if not scenes:
            raise ValueError("El proyecto no tiene escenas.")
        n = len(scenes)
        ctx.report = lambda msg, frac: prog(msg, frac)
        try:
            for i, sc in enumerate(scenes):
                if cancel and cancel():
                    raise Cancelled()
                prog(f"Preparando escena {i + 1}/{n}…", i / n * 0.0)
                sc.prepare()
                ctx.warnings.extend(sc.warnings)
        except Exception:
            for sc in scenes:
                sc.close()
            raise
        fps, W, H = ctx.fps, ctx.w, ctx.h
        frames = [max(1, round(sc.duration * fps)) for sc in scenes]
        total_frames = sum(frames)
        total_dur = total_frames / fps
        out_path = str(out_path)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        tmpdir = Path(tempfile.mkdtemp(prefix="vs_", dir=str(CACHE_DIR)))
        tmp_video = str(tmpdir / "video.mp4")
        enc = Encoder(tmp_video, W, H, fps, ctx.settings["encoder"], ctx.settings["quality"])
        tracks: list[tuple[str, float, float]] = []
        prev: Image.Image | None = None
        done, cursor = 0, 0
        tlen = round(float(ctx.settings["transition_seconds"]) * fps)
        try:
            for si, sc in enumerate(scenes):
                nf = frames[si]
                if sc.audio:
                    tracks.append((sc.audio, cursor / fps, sc.audio_vol))
                use_tr = prev is not None and sc.transition != "cut" and tlen > 0
                for fi in range(nf):
                    if cancel and cancel():
                        raise Cancelled()
                    img = sc.frame(fi / fps)
                    if use_tr and fi < tlen:
                        img = apply_transition(prev, img, (fi + 1) / (tlen + 1), sc.transition)
                    enc.write(img)
                    if fi == nf - 1:
                        prev = img.copy()
                    done += 1
                    if done % 6 == 0:
                        prog(f"Renderizando escena {si + 1}/{n}", done / total_frames)
                sc.close()
                cursor += nf
            enc.close()
            prog("Mezclando audio…", 0.995)
            try:
                from . import sfx as SX
                starts, cur2 = [], 0
                for nf_ in frames:
                    starts.append(cur2 / fps)
                    cur2 += nf_
                evs, w1 = SX.plan_events(scenes, starts, ctx.settings, tlen / fps)
                sx_tracks, w2 = SX.resolve_tracks(evs, ctx.settings, total_dur)
                tracks.extend(sx_tracks)
                for w_ in w1 + w2:
                    ctx.warnings.append(w_)
            except Exception as e_:
                print("Efectos de sonido omitidos:", e_)
            music = ctx.resolve(ctx.settings.get("music")) if ctx.settings.get("music") else None
            audio = mix_audio(tracks, total_dur, music, float(ctx.settings["music_volume"]),
                              str(tmpdir / "audio.m4a"), bool(ctx.settings.get("duck_music", True)))
            mux(tmp_video, audio, out_path, total_dur)
        except BaseException:
            enc.abort()
            raise
        finally:
            for sc in scenes:
                sc.close()
            try:
                for f in tmpdir.iterdir():
                    f.unlink()
                tmpdir.rmdir()
            except OSError:
                pass
        prog("Listo", 1.0)
        return {"path": out_path, "duration": total_dur, "frames": total_frames, "encoder": enc.used,
                "seconds": time.time() - t_start, "warnings": ctx.warnings}


def new_top_from_text(text: str, title: str = "", theme: str = "oscuro", countdown: bool = True,
                      intro: bool = True) -> dict:
    """Crea un proyecto de Top desde líneas 'Título | descripción | imagen(opcional)'."""
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        items.append({"title": parts[0], "text": parts[1] if len(parts) > 1 else "",
                      "media": [parts[2]] if len(parts) > 2 and parts[2] else []})
    n = len(items)
    scenes = []
    if intro and title:
        scenes.append({"type": "title", "title": title, "kicker": f"Top {n}", "narration": title})
    for i, it in enumerate(items):
        rank = n - i if countdown else i + 1
        scenes.append({"type": "top_item", "rank": str(rank), "title": it["title"], "text": it["text"],
                       "media": it["media"],
                       "narration": (it["title"] + ". " + it["text"]).strip(". ")})
    return {"settings": {"theme": theme}, "scenes": scenes}
