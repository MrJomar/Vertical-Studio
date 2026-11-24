"""Revisión automática de proyectos: dirección visual (ritmo, variedad), kit SVG y mapas.
Devuelve una lista de (nivel, mensaje) con nivel "error" | "aviso"."""
import json, math, re, unicodedata

WPS = 2.6  # palabras por segundo de la voz, para estimar duración


def _norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"[^a-z0-9 ]", "", "".join(c for c in t if unicodedata.category(c) != "Mn"))


def _words(t):
    return _norm(t).split()


def _km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _runs(vals, n):
    """Índices (1..) donde empieza una racha de n o más valores iguales consecutivos."""
    out, i = [], 0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[j + 1] == vals[i] and vals[i]:
            j += 1
        if j - i + 1 >= n:
            out.append((i + 1, j + 1, vals[i]))
        i = j + 1
    return out


def _parse_places(p):
    out = []
    if isinstance(p, str):
        for line in p.splitlines():
            line = line.strip()
            if not line:
                continue
            nm, _, rest = line.partition("|")
            try:
                la, lo = [float(v) for v in rest.split("|")[0].replace(";", ",").split(",")[:2]]
                out.append((nm.strip(), la, lo))
            except ValueError:
                out.append((nm.strip(), None, None))
    else:
        for q in p or []:
            if isinstance(q, str):
                out.append((q, None, None))
            else:
                out.append((q.get("name", ""), q.get("lat"), q.get("lon")))
    return out


def review(data):
    scenes = data["scenes"] if isinstance(data, dict) else data
    res = []
    add = lambda lvl, msg: res.append((lvl, msg))
    if not scenes:
        return [("error", "El proyecto no tiene escenas.")]
    est = []
    for n, sc in enumerate(scenes, 1):
        w = len(_words(sc.get("narration", "")))
        est.append(w / WPS)
        if not w:
            add("aviso", f"Escena {n}: sin narración.")
        elif w / WPS > 7.5:
            add("aviso", f"Escena {n}: ~{w / WPS:.0f} s de voz seguidos; divídela para cambiar de plano cada 2-5 s.")
        elif w / WPS < 1.2:
            add("aviso", f"Escena {n}: muy corta (~{w / WPS:.1f} s).")
    tot = sum(est)
    if tot < 25 or tot > 100:
        add("aviso", f"Duración estimada {tot:.0f} s (lo habitual en Shorts: 30-90 s).")
    if len(_words(scenes[0].get("narration", ""))) > 16:
        add("aviso", "Escena 1: el gancho es largo; arranca con una frase de 10 palabras o menos.")

    vec = [s for s in scenes if s.get("type") == "vector"]
    if vec:
        for a, b, v in _runs([s.get("bg") for s in scenes], 3):
            add("aviso", f"Escenas {a}-{b}: mismo fondo «{v}» {b - a + 1} veces seguidas.")
        for a, b, v in _runs([s.get("camera") for s in scenes], 3):
            add("aviso", f"Escenas {a}-{b}: misma cámara «{v}» {b - a + 1} veces seguidas.")
        try:
            from vstudio import svgkit
            e, w, nuevas = svgkit.check_project_data(data)
            res += [("error", x) for x in e] + [("aviso", x) for x in w]
            res += [("aviso", f"Pieza nueva pedida en escena {x['escena']}: {x.get('id')} — {x.get('descripcion', '')}") for x in nuevas]
        except Exception as ex:
            add("aviso", f"No pude revisar el kit SVG: {ex}")
        for n, sc in enumerate(scenes, 1):
            if sc.get("type") != "vector":
                continue
            lys = sc.get("layers") or []
            if not lys:
                add("aviso", f"Escena {n}: sin capas.")
            if len(lys) > 9:
                add("aviso", f"Escena {n}: {len(lys)} capas (demasiadas; deja 2-6).")
            if len([x for x in str(sc.get("fx", "")).split(",") if x.strip()]) > 3:
                add("aviso", f"Escena {n}: más de 3 efectos de ambiente.")
            wset = set(_words(sc.get("narration", "")))
            for ly in lys:
                for k in ("at", "out"):
                    v = ly.get(k)
                    if isinstance(v, str) and v.strip() and _norm(v).split()[0:1] and not set(_words(v)) <= wset:
                        add("aviso", f"Escena {n}: «{k}»=«{v}» no es una palabra exacta de la narración (no se sincronizará).")
            if not any((ly.get("w") or 0) >= 0.4 for ly in lys if ly.get("asset") != "texto"):
                add("aviso", f"Escena {n}: no hay un elemento protagonista grande (w ≥ 0.4).")

    maps = [(i, s) for i, s in enumerate(scenes, 1) if s.get("type") == "map"]
    if maps:
        try:
            from vstudio import geo
        except Exception:
            geo = None
        for n, sc in maps:
            pl = _parse_places(sc.get("places"))
            mode = sc.get("mode") or ("route" if len(pl) > 1 and not sc.get("highlight") else "zoom")
            for nm, la, lo in pl:
                if la is None:
                    add("aviso", f"Escena {n}: «{nm}» sin coordenadas; se buscará por nombre (necesita internet y puede fallar).")
                elif not (-90 <= la <= 90 and -180 <= lo <= 180):
                    add("error", f"Escena {n}: coordenadas imposibles para «{nm}» ({la}, {lo}); ¿latitud y longitud al revés?")
            if mode == "route":
                pts = [(la, lo) for _, la, lo in pl if la is not None]
                if len(pl) < 2:
                    add("error", f"Escena {n}: una ruta necesita 2 lugares o más.")
                fz = sc.get("follow_zoom")
                if len(pts) > 1 and fz:
                    ext = max(_km(a, b) for a in pts for b in pts)
                    if float(fz) * 40000 > ext * 3:
                        add("aviso", f"Escena {n}: follow_zoom={fz} es para rutas de ~{float(fz) * 40000:.0f} km y esta mide ~{ext:.0f} km; la cámara se aleja demasiado (quita follow_zoom o usa un valor menor).")
                for (a, b) in zip(pts, pts[1:]):
                    if _km(a, b) > 9000:
                        add("aviso", f"Escena {n}: salto de {_km(a, b):.0f} km entre dos puntos de la ruta (¿coordenada equivocada?).")
                    if _km(a, b) < 1:
                        add("aviso", f"Escena {n}: dos puntos seguidos casi iguales.")
            hl = sc.get("highlight") or []
            if isinstance(hl, str):
                hl = [x.strip() for x in hl.replace(";", ",").replace("\n", ",").split(",") if x.strip()]
            for h in hl:
                nm = h.partition(":")[0].strip()
                if geo and geo.find_country(nm) is None:
                    add("error", f"Escena {n}: no reconozco el país «{nm}».")
            if mode in ("zoom", "tour") and not pl and not hl and not sc.get("geojson"):
                add("error", f"Escena {n}: mapa sin lugares ni países.")
        for a, b, v in _runs([(s.get("highlight") if isinstance(s.get("highlight"), str) else json.dumps(s.get("highlight"))) if s.get("type") == "map" else None for s in scenes], 3):
            add("aviso", f"Escenas {a}-{b}: el mismo país resaltado {b - a + 1} veces seguidas; cambia de plano.")
        nz = [s.get("follow") for _, s in maps]
        if len(maps) >= 4 and not any(nz) and all((s.get("mode") or "") == "route" for _, s in maps):
            add("aviso", "Ninguna escena de ruta usa «follow» (cámara que sigue la ruta); el video puede verse estático.")
    return res


def review_file(path):
    with open(path, encoding="utf-8") as fh:
        return review(json.load(fh))


def map_prompt():
    from vstudio import styles
    return ("Eres productor de videos verticales tipo documental de mapas, en español. Cada día recibirás un TEMA y debes entregar UN proyecto "
            "completo en JSON para Vertical Studio: guion en escenas con su mapa satelital.\n\n"
            "Respuesta: SOLO este JSON, sin texto antes ni después ni comentarios:\n"
            '{"settings":{"theme":"oscuro","tts_engine":"gemini","map_style":"natural","map_grade":"vivo","caption_style":"suave"},"scenes":[ESCENAS]}\n\n'
            "Cada escena de mapa:\n"
            '{"type":"map","mode":"zoom|route|tour","narration":"1-2 frases (10-22 palabras)","duration":1.5,\n'
            ' "places":"Nombre | latitud, longitud\\nNombre | latitud, longitud",   // una línea por lugar, coordenadas en grados decimales (lat primero), SIEMPRE con coordenadas\n'
            ' "highlight":"País:#22c55e, Otro país:#ef4444",   // opcional; nombres de país en español o inglés\n'
            ' "route_color":"#f2ff2e","route_width":11,"follow":true,"follow_zoom":0.3,"tilt":14,   // solo en mode route\n'
            ' "route_labels":[{"frac":0.5,"text":"30,000 km","style":"etiqueta","size":0.3}],   // rótulos sobre la ruta (cifras)\n'
            ' "intro":"blanco"}   // opcional: destello al entrar\n\n'
            "REGLAS: 1) Usa solo datos que puedas afirmar con seguridad; si dudas de una cifra, redondea o quítala. "
            "2) Revisa que cada coordenada corresponda de verdad al lugar (latitud primero; sur y oeste son negativos). "
            "3) En una ruta, pon los puntos en orden de recorrido y con paradas intermedias (no saltos de más de 3000 km). "
            "4) Cambia de plano cada escena: alterna zoom, route y países resaltados; no repitas el mismo país más de 2 escenas seguidas. "
            "5) Escena 1 = gancho con una cifra o paradoja en 10 palabras o menos. 6) Cierra con un giro de perspectiva. "
            "7) Entre 8 y 12 escenas. 8) \"duration\" siempre 1.5: la escena dura lo que dura la voz.\n"
            + styles.style_block("mapa_ruta"))
