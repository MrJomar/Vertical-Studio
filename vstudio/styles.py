"""Estilos de guion/producción: estilos/*.json (+ privados en cache/estilos_privados/)."""
import json, os

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRS = [os.path.join(APP_DIR, "estilos"), os.path.join(APP_DIR, "cache", "estilos_privados")]


def list_styles(tipo=None):
    out = []
    for d in DIRS:
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".json"):
                continue
            try:
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    s = json.load(fh)
            except Exception:
                continue
            s.setdefault("id", f[:-5])
            s["privado"] = d != DIRS[0]
            if not tipo or s.get("tipo") == tipo:
                out.append(s)
    return out


def get(style_id):
    for s in list_styles():
        if s["id"] == style_id:
            return s
    return None


def _rng(v):
    return f"{v[0]}–{v[1]}" if isinstance(v, (list, tuple)) and len(v) == 2 else str(v)


def style_block(style_id):
    """Texto de reglas de estilo para añadir a cualquier prompt."""
    s = get(style_id)
    if not s:
        return ""
    reglas = "\n".join(f"- {r}" for r in s.get("reglas_guion", []))
    return (f"\nESTILO: {s.get('nombre', style_id)}\n"
            f"Duración total: {_rng(s.get('duracion_total_s', ''))} s. Cada escena: {_rng(s.get('escena_s', ''))} s. "
            f"Frases de {_rng(s.get('palabras_por_frase', ''))} palabras.\n"
            f"Estructura: {' → '.join(s.get('estructura', []))}.\n"
            f"Reglas:\n{reglas}\n"
            f"Recursos visuales a usar: {', '.join(s.get('recursos_visuales', []))}.\n"
            f"Tono de voz: {s.get('voz', {}).get('tono', '')}.\n")


def script_prompt(style_id, tema="", canal=""):
    """Prompt para que una IA proponga ideas o escriba el guion en ese estilo."""
    s = get(style_id)
    if not s:
        return ""
    return ("Eres guionista de videos verticales de YouTube Shorts en español. "
            "Escribe UN guion completo, solo la narración, una frase por línea, sin títulos ni acotaciones, "
            "siguiendo estrictamente este estilo." + style_block(style_id) +
            (f"\nCanal/tono: {canal}\n" if canal else "") +
            (f"\nTEMA: {tema}\n" if tema else "\nPrimero propón 5 ideas con un gancho cada una y espera a que elija.\n"))
