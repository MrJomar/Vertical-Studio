#!/usr/bin/env python3
"""Vertical Studio — línea de comandos.

  python cli.py render proyecto.json -o salida.mp4
  python cli.py preview proyecto.json --scene 0 --t 1.5 -o cuadro.png
  python cli.py autoclip video.mp4 -n 5 --min 20 --max 55 -o proyecto.json
"""
import argparse
import sys
import time

from vstudio.project import Project


def _progress(stage, frac):
    sys.stdout.write(f"\r{stage:<40} {frac * 100:5.1f}%")
    sys.stdout.flush()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="verticalstudio")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="Renderiza un proyecto a MP4")
    r.add_argument("project")
    r.add_argument("-o", "--out", default=None)
    r.add_argument("--encoder", choices=["auto", "nvenc", "x264"], default=None)
    r.add_argument("--quality", choices=["borrador", "normal", "alta", "maxima"], default=None)

    p = sub.add_parser("preview", help="Guarda un cuadro de una escena en PNG")
    p.add_argument("project")
    p.add_argument("--scene", type=int, default=0)
    p.add_argument("--t", type=float, default=None)
    p.add_argument("-o", "--out", default="preview.png")

    c = sub.add_parser("autoclip", help="Propone clips de un video largo")
    c.add_argument("video")
    c.add_argument("-n", type=int, default=5)
    c.add_argument("--min", type=float, default=20)
    c.add_argument("--max", type=float, default=55)
    c.add_argument("--fit", choices=["blur", "cover", "face"], default="blur")
    c.add_argument("--model", default="small")
    c.add_argument("--language", default=None)
    c.add_argument("--gemini-key", default=None)
    c.add_argument("-o", "--out", default="proyecto.json")

    a = ap.parse_args(argv)
    if a.cmd == "render":
        proj = Project.load(a.project)
        if a.encoder:
            proj.settings["encoder"] = a.encoder
        if a.quality:
            proj.settings["quality"] = a.quality
        out = a.out or a.project.rsplit(".", 1)[0] + ".mp4"
        info = proj.render(out, _progress)
        print(f"\nListo: {info['path']}  ({info['duration']:.1f}s, {info['encoder']}, {info['seconds']:.0f}s de render)")
        for w in info["warnings"]:
            print("Aviso:", w)
    elif a.cmd == "preview":
        proj = Project.load(a.project)
        proj.preview_frame(a.scene, a.t).save(a.out)
        print("Guardado", a.out)
    elif a.cmd == "autoclip":
        import json
        from vstudio import clipper
        clips = clipper.analyze(a.video, a.n, a.min, a.max, a.model, a.language, a.gemini_key,
                                progress=lambda f: _progress("Transcribiendo", f))
        print()
        for i, cl in enumerate(clips, 1):
            print(f" {i}. {cl['start']:.1f}s → {cl['end']:.1f}s  {cl.get('title', '')}")
        data = {"settings": {"theme": "oscuro"}, "scenes": clipper.to_scenes(a.video, clips, a.fit)}
        open(a.out, "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False, indent=2))
        print("Proyecto creado:", a.out)


if __name__ == "__main__":
    main()
