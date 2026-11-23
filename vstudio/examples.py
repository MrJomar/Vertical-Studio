"""Ejemplos incluidos: un proyecto de muestra por cada tipo de video."""
from __future__ import annotations

import copy

from .core import APP_DIR

ASSETS = APP_DIR / "examples" / "assets"


def _a(name: str) -> str:
    return str(ASSETS / name)


def _top():
    return {"settings": {"theme": "neon", "tts_engine": "silencio", "watermark": "@tucanal"}, "scenes": [
        {"type": "title", "kicker": "Top 3", "title": "Los 3 barrios más antiguos", "subtitle": "Así se ve un Top",
         "narration": "Estos son los tres barrios más antiguos de la ciudad."},
        {"type": "top_item", "rank": "3", "title": "Coyoacán", "text": "Calles empedradas y plazas llenas de historia.",
         "media": [_a("foto1.jpg")], "narration": "En el lugar tres, Coyoacán, con sus calles empedradas y plazas llenas de historia."},
        {"type": "top_item", "rank": "2", "title": "Tlatelolco", "text": "La antigua ciudad gemela de Tenochtitlan.",
         "media": [_a("foto2.jpg")], "narration": "En el lugar dos, Tlatelolco, la antigua ciudad gemela de Tenochtitlan."},
        {"type": "top_item", "rank": "1", "title": "Xochimilco", "text": "Chinampas que sobreviven desde la época prehispánica.",
         "media": [_a("foto3.jpg"), _a("foto1.jpg")], "narration": "Y en el primer lugar, Xochimilco, con chinampas que sobreviven desde la época prehispánica."}]}


def _map_zoom():
    return {"settings": {"theme": "oscuro", "tts_engine": "silencio", "map_style": "satelite"}, "scenes": [
        {"type": "map", "title": "México", "mode": "zoom", "highlight": "México",
         "narration": "Empezamos en México, un país con más de dos mil años de historia.", "duration": 7}]}


def _map_tour():
    return {"settings": {"theme": "oscuro", "tts_engine": "silencio", "map_style": "satelite"}, "scenes": [
        {"type": "map", "title": "Gira por México", "mode": "tour", "duration": 12, "place_zoom": 0.012,
         "places": "Ciudad de México | 19.4326, -99.1332\nGuadalajara | 20.6597, -103.3496\nMonterrey | 25.6866, -100.3161",
         "narration": "Visitamos la capital, luego Guadalajara y terminamos en Monterrey."}]}


def _map_route():
    return {"settings": {"theme": "oscuro", "tts_engine": "silencio", "map_style": "oscuro"}, "scenes": [
        {"type": "map", "title": "Ruta transatlántica", "mode": "route", "marker": "arrow", "duration": 9,
         "route_style": "arc", "places": "Lima | -12.05, -77.04\nBogotá | 4.71, -74.07\nMadrid | 40.42, -3.70",
         "narration": "De Lima a Bogotá y de ahí cruzamos el Atlántico hasta Madrid.",
         "overlays": [{"asset": "etiqueta", "place": "Bogotá", "text": "8.000 km", "at": "Bogotá", "w": 0.3, "dy": 90, "anim": "pop+float"},
                      {"asset": "calendario", "place": "Madrid", "month": "ENE", "day": "12", "at": "Madrid", "w": 0.15}]}]}


def _broll():
    return {"settings": {"theme": "papel", "tts_engine": "silencio"}, "scenes": [
        {"type": "broll", "title": "Una ciudad que no duerme", "media": [_a("foto1.jpg"), _a("foto2.jpg"), _a("foto3.jpg")],
         "narration": "Cada mañana la ciudad despierta con el ruido de los mercados, las campanas y el olor del café recién hecho.",
         "duration": 8}]}


def _clip():
    return {"settings": {"theme": "neon", "tts_engine": "silencio"}, "scenes": [
        {"type": "clip", "source": _a("clip_demo.mp4"), "start": "0", "end": "8", "fit": "blur",
         "hook": "Mira lo que pasa aquí", "captions": False}]}


def _vector():
    st = {"theme": "oscuro", "tts_engine": "silencio", "caption_style": "caja"}
    return {"settings": st, "scenes": [
        {"type": "vector", "bg": "azulejos", "camera": "push",
         "narration": "¿Por qué a veces huele a pescado? La culpable es la trimetilamina.",
         "layers": [
             {"asset": "hielo", "x": 0.5, "y": 0.86, "w": 1.05, "anim": "fade", "z": 1},
             {"asset": "banda", "x": 0.5, "y": 0.94, "w": 1.0, "anim": "slide_up", "text": "PESCADERÍA", "z": 5},
             {"asset": "pez", "x": 0.5, "y": 0.72, "w": 0.78, "anim": "slide_left+float", "z": 2},
             {"asset": "olor", "x": 0.5, "y": 0.5, "w": 0.3, "at": "huele", "anim": "fade+float", "z": 3}]},
        {"type": "vector", "bg": "niebla",
         "narration": "Es una molécula con cara de villano que se escapa al aire.",
         "layers": [
             {"asset": "villano", "x": 0.5, "y": 0.52, "w": 0.62, "anim": "pop+float"},
             {"asset": "etiqueta", "x": 0.5, "y": 0.8, "w": 0.4, "at": "molécula", "text": "N(CH₃)₃", "color": "#1d7a2a", "anim": "pop"}]},
        {"type": "vector", "bg": "olas",
         "narration": "Normalmente la vagina está ácida y esas bacterias buenas la protegen.",
         "layers": [
             {"asset": "bacteria_buena", "count": 9, "spread": [0.08, 0.25, 0.92, 0.95], "w": 0.24, "anim": "pop+drift", "at": 0.1},
             {"asset": "medidor", "x": 0.5, "y": 0.6, "w": 0.72, "at": "ácida", "anim": "pop", "value": 4, "z": 9}]},
        {"type": "vector", "bg": "olas", "bg_colors": ["#7a6ad8", "#2a1a6a", "#a89cff"],
         "narration": "Pero si el pH sube, las bacterias malas invaden y el olor aparece.",
         "layers": [
             {"asset": "bacteria_mala", "count": 11, "spread": [0.1, 0.22, 0.9, 0.92], "w": 0.24, "anim": "pop+drift", "at": "bacterias"},
             {"asset": "medidor", "x": 0.5, "y": 0.62, "w": 0.72, "anim": "pop", "value_from": 4, "value_to": 8, "value_dur": 2.5, "at": 0.3, "z": 9}]},
        {"type": "vector", "bg": "cuarto",
         "narration": "Y después de tener relaciones, aparece el cartel de no molestar.",
         "layers": [
             {"asset": "puerta", "x": 0.5, "y": 0.52, "w": 0.55, "anim": "fade"},
             {"asset": "cartel", "x": 0.62, "y": 0.58, "w": 0.32, "at": "cartel", "anim": "drop+wobble", "z": 5},
             {"asset": "corazon", "count": 8, "spread": [0.2, 0.3, 0.8, 0.9], "w": 0.05, "anim": "rise+fade", "color": "#ff8fb8"}]},
        {"type": "vector", "bg": "rayos",
         "narration": "Tranquila: le pasa a una de cada tres mujeres y un médico lo puede tratar.",
         "layers": [
             {"asset": "persona", "count": 15, "layout": "grid", "cols": 5, "spread": [0.16, 0.5, 0.84, 0.88], "w": 0.2, "anim": "pop+bounce", "amp": 0.3},
             {"asset": "pastilla", "x": 0.5, "y": 0.3, "w": 0.32, "at": "médico", "anim": "pop+wobble", "rot": -25}]}]}


CATALOG = [
    {"id": "vector", "type": "vector", "title": "Animación vectorial (explicativo)",
     "desc": "Personajes, objetos y fondos animados por capas, con subtítulos resaltados y sincronía con la voz.", "build": _vector},
    {"id": "map_zoom", "type": "map", "title": "Mapa: zoom a un país",
     "desc": "Vuela por el mapa real hasta un país y lo resalta. Necesita internet la primera vez (teselas).", "build": _map_zoom},
    {"id": "map_tour", "type": "map", "title": "Mapa: visitar lugares",
     "desc": "Cámara que viaja de ciudad en ciudad con pines y rótulos sobre imagen satelital.", "build": _map_tour},
    {"id": "map_route", "type": "map", "title": "Mapa: ruta animada",
     "desc": "Una ruta que se dibuja en arco entre varios puntos con un marcador en movimiento.", "build": _map_route},
    {"id": "broll", "type": "broll", "title": "B-roll con voz",
     "desc": "Imágenes o clips con fundidos, narración con voz IA y subtítulos palabra por palabra.", "build": _broll},
    {"id": "clip", "type": "clip", "title": "Clip de video largo",
     "desc": "Un tramo de un video horizontal convertido a vertical con fondo difuminado y gancho. Con Whisper añade subtítulos.", "build": _clip},
]


def example_project(ex_id: str) -> dict:
    for ex in CATALOG:
        if ex["id"] == ex_id:
            return copy.deepcopy(ex["build"]())
    raise KeyError(ex_id)
