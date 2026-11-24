"""Kit de piezas SVG: catálogo automático (assets/svg/) y prompt para que una IA componga escenas con él."""
import json, os, re
import xml.etree.ElementTree as ET

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRS = [os.path.join(APP_DIR, "assets", "svg"), os.path.join(APP_DIR, "cache", "svg_privados")]


def _meta():
    out = {}
    for d in DIRS:
        p = os.path.join(d, "catalogo.json")
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    out.update({k: v for k, v in json.load(fh).items() if not k.startswith("_")})
            except Exception:
                pass
    return out


def scan():
    """Lista de piezas: lee cada SVG (grupos, variables, proporción) y lo une con catalogo.json."""
    meta, items = _meta(), []
    for d in DIRS:
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.lower().endswith(".svg"):
                continue
            pid = f[:-4]
            m = meta.get(pid, {})
            if m.get("obsoleta"):
                continue
            try:
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    txt = fh.read()
                variables = sorted(set(re.findall(r"\{\{\s*([\w-]+)", txt)))
                clean = re.sub(r"\{\{\s*[\w-]+\s*(?:\|([^}]*))?\}\}", lambda x: x.group(1) or "0", txt)
                root = ET.fromstring(clean)
                vb = [float(v) for v in re.split(r"[ ,]+", root.get("viewBox", "0 0 100 100").strip())]
                grupos = [c.get("id") for c in root if c.tag.split("}")[-1] == "g" and c.get("id")]
                alto = round(vb[3] / vb[2], 2)
            except Exception as e:
                items.append({"id": pid, "error": str(e)})
                continue
            items.append({"id": pid, "nombre": m.get("nombre", pid), "descripcion": m.get("descripcion", ""),
                          "usos": m.get("usos", ""), "w": m.get("w"), "nota": m.get("nota", ""),
                          "grupos": grupos, "partes": m.get("partes", {}), "variables": variables,
                          "alto_rel": alto, "privada": d != DIRS[0], "sin_descripcion": pid not in meta})
    return items


def _linea(it):
    w = it.get("w") or [0.4, 0.9]
    partes = ", ".join(f"{g} ({it['partes'][g]})" if g in it.get("partes", {}) else g for g in it["grupos"]) or "una sola pieza"
    vs = ", ".join(it["variables"]) or "—"
    s = (f'- "{it["id"]}" — {it["nombre"]}: {it["descripcion"]} Úsalo para: {it["usos"]}.\n'
         f'  Partes (para only/hide): {partes}. Variables: {vs}. Ancho w recomendado {w[0]}–{w[1]}; su alto es {it["alto_rel"]} veces su ancho.')
    if it.get("nota"):
        s += f' {it["nota"]}'
    return s


def catalog_text():
    return "\n".join(_linea(i) for i in scan() if "error" not in i)


def markdown():
    rows = ["# Catálogo del kit SVG", "", "Generado por `python cli.py kit`. No lo edites a mano: edita `catalogo.json`.", ""]
    for i in scan():
        if "error" in i:
            rows.append(f"- **{i['id']}**: ERROR {i['error']}")
            continue
        rows += [f"## {i['id']} — {i['nombre']}", i["descripcion"], "",
                 f"- Usos: {i['usos']}", f"- Partes: {', '.join(i['grupos']) or '—'}",
                 f"- Variables: {', '.join(i['variables']) or '—'}", f"- Ancho recomendado: {i['w']}  · alto/ancho: {i['alto_rel']}"]
        if i.get("nota"):
            rows.append(f"- Nota: {i['nota']}")
        if i["sin_descripcion"]:
            rows.append("- ⚠ Sin descripción en catalogo.json")
        rows.append("")
    return "\n".join(rows)


def kit_prompt(style=""):
    """Prompt completo para una IA programada: escribe el proyecto del día usando solo piezas del kit."""
    from vstudio import scenes  # noqa: F401  (evita importación circular)
    from vstudio.vector import ai_prompt
    cab = ("Eres productor de videos verticales explicativos. Cada día recibirás un TEMA y debes entregar UN proyecto "
           "completo en JSON, listo para cargar en Vertical Studio: guion dividido en escenas + animación compuesta con las piezas del kit.\n\n"
           "PASOS: 1) escribe el guion (frases cortas). 2) divide en escenas de 2-6 s. 3) para cada escena elige fondo, piezas del kit y textos. "
           "4) responde SOLO con el JSON del proyecto: {\"settings\":{\"theme\":\"oscuro\",\"tts_engine\":\"gemini\",\"caption_style\":\"suave\"},\"scenes\":[...]}. "
           "En cada escena pon \"duration\":1.5 (es solo un mínimo; la escena dura lo que dura la voz).\n\n"
           "REGLA DEL KIT: para dibujar cuerpo, órganos, personas y objetos usa SIEMPRE piezas del kit con {\"asset\":\"svg\",\"file\":\"<id>\",...}. "
           "No inventes SVG ni uses piezas que no estén en la lista. Si el guion necesita algo que el kit no tiene, usa la pieza más cercana y añade en esa escena "
           "\"piezas_nuevas\":[{\"id\":\"nombre_corto\",\"descripcion\":\"qué debería dibujarse\"}] para que se cree después.\n\n"
           "PIEZAS SVG DEL KIT (asset \"svg\", parámetro \"file\"; \"only\"/\"hide\" eligen partes; las variables se pasan como parámetros de la capa, p. ej. \"nervio\":\"#ff9a8a\"):\n")
    fin = ("\n\nIMPORTANTE: el bloque anterior describe el formato de cada escena. Tu respuesta final es el objeto del proyecto "
           "{\"settings\":{...},\"scenes\":[ ...esas escenas... ]}, sin texto antes ni después y sin comentarios dentro del JSON.")
    return cab + catalog_text() + "\n\n" + ai_prompt(style) + fin


def check_project(path):
    """Revisa un proyecto JSON contra el kit: piezas que no existen, partes (only/hide) inválidas, ancho fuera de rango.
    Devuelve (errores, avisos, piezas_nuevas)."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    kit = {i["id"]: i for i in scan() if "error" not in i}
    errs, warns, nuevas = [], [], []
    scenes = data["scenes"] if isinstance(data, dict) else data
    for n, sc in enumerate(scenes, 1):
        for pn in sc.get("piezas_nuevas", []) or []:
            nuevas.append({"escena": n, **pn})
        for ly in sc.get("layers", []) or []:
            if ly.get("asset") != "svg" or ly.get("svg"):
                continue
            f = str(ly.get("file", "")).replace(".svg", "")
            it = kit.get(f)
            if not it:
                errs.append(f"Escena {n}: la pieza «{f}» no existe en el kit")
                continue
            for k in ("only", "hide"):
                for g in [x.strip() for x in str(ly.get(k) or "").split(",") if x.strip()]:
                    if g not in it["grupos"]:
                        errs.append(f"Escena {n}: «{f}» no tiene la parte «{g}» (tiene: {', '.join(it['grupos']) or 'ninguna'})")
            w = ly.get("w")
            if it.get("w") and isinstance(w, (int, float)) and not (it["w"][0] * 0.6 <= w <= it["w"][1] * 1.4):
                warns.append(f"Escena {n}: «{f}» con w={w} (recomendado {it['w'][0]}–{it['w'][1]})")
            alto = (w or 0.5) * it["alto_rel"] * 0.5625
            y = ly.get("y", 0.5)
            if isinstance(y, (int, float)) and (y - alto / 2 < -0.05 or y + alto / 2 > 1.05):
                warns.append(f"Escena {n}: «{f}» se sale de la pantalla (y={y}, w={w})")
    return errs, warns, nuevas
