"""Datos geográficos (Natural Earth vía world-atlas), proyección Mercator y dibujo vectorial con OpenCV."""
from __future__ import annotations

import json
import math
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

import cv2
import numpy as np

from .core import CACHE_DIR, DATA_DIR

# --------------------------------------------------------------------------- proyección
MAX_LAT = 85.0511


def to_world(lon, lat):
    """lon/lat (grados) → coordenadas mundo Mercator [0,1]²."""
    lon = np.asarray(lon, dtype=np.float64)
    lat = np.clip(np.asarray(lat, dtype=np.float64), -MAX_LAT, MAX_LAT)
    x = (lon + 180.0) / 360.0
    y = 0.5 - np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)) / (2 * np.pi)
    return x, y


def world_to_lonlat(x, y):
    lon = x * 360.0 - 180.0
    lat = np.degrees(2 * np.arctan(np.exp((0.5 - y) * 2 * np.pi)) - np.pi / 2)
    return lon, lat


def project(pts: np.ndarray, cam, w: int, h: int) -> np.ndarray:
    cx, cy, span = cam
    s = w / span
    out = np.empty_like(pts)
    out[:, 0] = (pts[:, 0] - cx) * s + w / 2
    out[:, 1] = (pts[:, 1] - cy) * s + h / 2
    return out


def fit_span(bounds, w: int, h: int, margin: float = 0.3, min_span: float = 0.0004) -> float:
    xmin, ymin, xmax, ymax = bounds
    bw, bh = max(xmax - xmin, 1e-9), max(ymax - ymin, 1e-9)
    return max(min_span, bw * (1 + margin), bh * (1 + margin) * w / h)


# --------------------------------------------------------------------------- nombres
def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()
    return " ".join(s.replace(".", " ").replace("-", " ").split())


ES_ALIASES = {
    "estados unidos": "United States of America", "eeuu": "United States of America", "usa": "United States of America",
    "ee uu": "United States of America", "mexico": "Mexico", "canada": "Canada", "espana": "Spain",
    "alemania": "Germany", "francia": "France", "italia": "Italy", "japon": "Japan", "china": "China",
    "india": "India", "brasil": "Brazil", "argentina": "Argentina", "chile": "Chile", "colombia": "Colombia",
    "peru": "Peru", "venezuela": "Venezuela", "reino unido": "United Kingdom", "inglaterra": "United Kingdom",
    "gran bretana": "United Kingdom", "rusia": "Russia", "egipto": "Egypt", "turquia": "Turkey",
    "grecia": "Greece", "suiza": "Switzerland", "suecia": "Sweden", "noruega": "Norway", "dinamarca": "Denmark",
    "finlandia": "Finland", "polonia": "Poland", "ucrania": "Ukraine", "corea del sur": "South Korea",
    "corea del norte": "North Korea", "arabia saudita": "Saudi Arabia", "arabia saudi": "Saudi Arabia",
    "sudafrica": "South Africa", "australia": "Australia", "nueva zelanda": "New Zealand",
    "marruecos": "Morocco", "nigeria": "Nigeria", "etiopia": "Ethiopia", "irlanda": "Ireland",
    "paises bajos": "Netherlands", "holanda": "Netherlands", "belgica": "Belgium", "austria": "Austria",
    "portugal": "Portugal", "cuba": "Cuba", "guatemala": "Guatemala", "honduras": "Honduras",
    "el salvador": "El Salvador", "nicaragua": "Nicaragua", "costa rica": "Costa Rica", "panama": "Panama",
    "ecuador": "Ecuador", "bolivia": "Bolivia", "paraguay": "Paraguay", "uruguay": "Uruguay",
    "republica dominicana": "Dominican Rep.", "iran": "Iran", "irak": "Iraq", "israel": "Israel",
    "indonesia": "Indonesia", "filipinas": "Philippines", "tailandia": "Thailand", "vietnam": "Vietnam",
    "pakistan": "Pakistan", "afganistan": "Afghanistan", "mongolia": "Mongolia", "groenlandia": "Greenland",
    "islandia": "Iceland", "fiyi": "Fiji", "fiji": "Fiji", "republica checa": "Czechia", "chequia": "Czechia", "hungria": "Hungary",
    "rumania": "Romania", "rumanía": "Romania", "bulgaria": "Bulgaria", "serbia": "Serbia", "croacia": "Croatia",
    "kenia": "Kenya", "argelia": "Algeria", "tunez": "Tunisia", "libia": "Libya", "sudan": "Sudan",
    "congo": "Dem. Rep. Congo", "tanzania": "Tanzania", "angola": "Angola", "mozambique": "Mozambique",
    "madagascar": "Madagascar", "ghana": "Ghana", "senegal": "Senegal", "camerun": "Cameroon",
    "emiratos arabes unidos": "United Arab Emirates", "qatar": "Qatar", "jordania": "Jordan", "libano": "Lebanon",
    "siria": "Syria", "nepal": "Nepal", "bangladesh": "Bangladesh", "sri lanka": "Sri Lanka", "myanmar": "Myanmar",
    "birmania": "Myanmar", "camboya": "Cambodia", "laos": "Laos", "malasia": "Malaysia", "singapur": "Singapore",
    "taiwan": "Taiwan", "kazajistan": "Kazakhstan", "uzbekistan": "Uzbekistan", "papua nueva guinea": "Papua New Guinea",
    "puerto rico": "Puerto Rico", "jamaica": "Jamaica", "haiti": "Haiti", "belice": "Belize", "guyana": "Guyana",
    "surinam": "Suriname", "bielorrusia": "Belarus", "lituania": "Lithuania", "letonia": "Latvia", "estonia": "Estonia",
    "eslovaquia": "Slovakia", "eslovenia": "Slovenia", "albania": "Albania", "bosnia": "Bosnia and Herz.",
    "macedonia del norte": "North Macedonia", "moldavia": "Moldova", "armenia": "Armenia", "georgia": "Georgia",
    "azerbaiyan": "Azerbaijan", "luxemburgo": "Luxembourg", "chipre": "Cyprus", "somalia": "Somalia",
    "uganda": "Uganda", "zimbabue": "Zimbabwe", "zambia": "Zambia", "namibia": "Namibia", "botsuana": "Botswana",
}


# --------------------------------------------------------------------------- estructuras
class Poly:
    __slots__ = ("ext", "holes", "bbox", "area", "offsets")

    def __init__(self, ext: np.ndarray, holes: list[np.ndarray]):
        self.ext, self.holes = ext, holes
        self.bbox = (float(ext[:, 0].min()), float(ext[:, 1].min()), float(ext[:, 0].max()), float(ext[:, 1].max()))
        self.area = (self.bbox[2] - self.bbox[0]) * (self.bbox[3] - self.bbox[1])
        # copias del mundo en las que hay que dibujar el polígono (cruza el borde ±180°)
        self.offsets = (0.0,) + ((-1.0,) if self.bbox[2] > 1.0 else ()) + ((1.0,) if self.bbox[0] < 0.0 else ())


class Feature:
    def __init__(self, name: str, fid: str, polys: list[Poly]):
        self.name, self.id, self.polys = name, fid, polys
        self.main = max(polys, key=lambda p: p.area) if polys else None
        self.area = self.main.area if self.main else 0.0

    @property
    def bounds(self):
        """Caja del polígono principal (evita que territorios lejanos arruinen el encuadre)."""
        return self.main.bbox

    @property
    def center(self):
        b = self.main.bbox
        return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)

    @property
    def full_bounds(self):
        bs = [p.bbox for p in self.polys]
        return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))


def _ring_world(lonlat: np.ndarray) -> np.ndarray:
    x, y = to_world(lonlat[:, 0], lonlat[:, 1])
    dx = np.diff(x)
    jumps = np.round(dx)  # saltos de ±1 = cruce del antimeridiano → se "desenrolla" el anillo
    if np.any(jumps != 0):
        x = x - np.concatenate([[0.0], np.cumsum(jumps)])
    return np.stack([x, y], axis=1)


def _decode_topology(topo: dict) -> list[Feature]:
    tr = topo.get("transform")
    arcs = []
    for arc in topo["arcs"]:
        a = np.array(arc, dtype=np.float64)
        if tr:
            a = np.cumsum(a, axis=0)
            a[:, 0] = a[:, 0] * tr["scale"][0] + tr["translate"][0]
            a[:, 1] = a[:, 1] * tr["scale"][1] + tr["translate"][1]
        arcs.append(a)

    def ring(idx):
        pts = []
        for i in idx:
            a = arcs[i] if i >= 0 else arcs[~i][::-1]
            pts.append(a if not pts else a[1:])
        return np.vstack(pts)

    feats = []
    obj = next(iter(topo["objects"].values()))
    for g in obj["geometries"]:
        t = g.get("type")
        if t == "Polygon":
            polys_arcs = [g["arcs"]]
        elif t == "MultiPolygon":
            polys_arcs = g["arcs"]
        else:
            continue
        polys = []
        for pa in polys_arcs:
            rings = [_ring_world(ring(r)) for r in pa]
            if len(rings[0]) >= 3:
                polys.append(Poly(rings[0], rings[1:]))
        name = (g.get("properties") or {}).get("name") or str(g.get("id"))
        if polys:
            feats.append(Feature(name, str(g.get("id")), polys))
    feats.sort(key=lambda f: -f.area)
    return feats


_cache: dict = {}


def load_countries(res: str = "50m") -> list[Feature]:
    if res not in _cache:
        topo = json.loads((DATA_DIR / f"countries-{res}.json").read_text("utf-8"))
        _cache[res] = _decode_topology(topo)
    return _cache[res]


def resolution_for(span: float) -> str:
    if span > 0.30:
        return "110m"
    if span > 0.012:
        return "50m"
    return "10m"


def find_country(name: str, res: str = "50m") -> Feature | None:
    feats = load_countries(res)
    n = norm(name)
    target = norm(ES_ALIASES.get(n, name))
    for f in feats:
        if norm(f.name) == target:
            return f
    for f in feats:
        if target and (norm(f.name).startswith(target) or target in norm(f.name)):
            return f
    for f in feats:
        if f.id == name.strip():
            return f
    return None


_NAME_KEYS = ("name", "nombre", "NAME", "NOMBRE", "NOM_COL", "NOM_MUN", "NOMGEO", "alcaldia", "colonia", "nom_ent",
              "NAME_1", "NAME_2", "admin", "ADMIN", "label")


def load_geojson(path: str, name_key: str | None = None) -> list[Feature]:
    data = json.loads(Path(path).read_text("utf-8"))
    if data.get("type") == "FeatureCollection":
        items = data["features"]
    elif data.get("type") == "Feature":
        items = [data]
    else:
        items = [{"type": "Feature", "geometry": data, "properties": {}}]
    feats = []
    for i, it in enumerate(items):
        g = it.get("geometry") or {}
        props = it.get("properties") or {}
        if g.get("type") == "Polygon":
            polys_c = [g["coordinates"]]
        elif g.get("type") == "MultiPolygon":
            polys_c = g["coordinates"]
        else:
            continue
        polys = []
        for pc in polys_c:
            rings = [_ring_world(np.array(r, dtype=np.float64)[:, :2]) for r in pc]
            if len(rings[0]) >= 3:
                polys.append(Poly(rings[0], rings[1:]))
        key = name_key if name_key and name_key in props else next((k for k in _NAME_KEYS if k in props), None)
        name = str(props.get(key)) if key else f"zona {i + 1}"
        if polys:
            feats.append(Feature(name, str(i), polys))
    feats.sort(key=lambda f: -f.area)
    return feats


# --------------------------------------------------------------------------- geocodificación
def geocode(place: str) -> tuple[float, float]:
    """(lat, lon) vía Nominatim/OpenStreetMap, con caché en disco."""
    cfile = CACHE_DIR / "geocode.json"
    cache = {}
    if cfile.exists():
        try:
            cache = json.loads(cfile.read_text("utf-8"))
        except Exception:
            cache = {}
    k = norm(place)
    if k in cache:
        return tuple(cache[k])
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": place, "format": "json", "limit": 1})
    req = urllib.request.Request(url, headers={"User-Agent": "VerticalStudio/1.0 (local video tool)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"No pude ubicar '{place}' (sin internet?). Escribe lat/lon manualmente. ({e})")
    if not res:
        raise RuntimeError(f"No encontré el lugar '{place}'. Prueba con otro nombre o escribe lat/lon.")
    cache[k] = [float(res[0]["lat"]), float(res[0]["lon"])]
    cfile.write_text(json.dumps(cache), "utf-8")
    time.sleep(1.0)  # política de uso de Nominatim
    return tuple(cache[k])


# --------------------------------------------------------------------------- dibujo
def _px16(pts: np.ndarray) -> np.ndarray:
    return np.round(np.clip(pts, -3e6, 3e6) * 16).astype(np.int32)


def draw_features(img: np.ndarray, feats: list[Feature], cam, fills: dict, default_fill, outline=None,
                  line_w: int = 1, skip=(), only: set | None = None, outline_map: dict | None = None) -> None:
    h, w = img.shape[:2]
    cx, cy, span = cam
    s = w / span
    x0, x1 = cx - span / 2, cx + span / 2
    y0, y1 = cy - span * h / w / 2, cy + span * h / w / 2
    for f in feats:
        if f.name in skip or (only is not None and f.name not in only):
            continue
        fill = fills.get(f.name, default_fill)
        oc = (outline_map or {}).get(f.name, outline)
        for p in f.polys:
            bx0, by0, bx1, by1 = p.bbox
            if by1 < y0 or by0 > y1:
                continue
            if (bx1 - bx0) * s < 0.6 and (by1 - by0) * s < 0.6:
                continue
            for off in p.offsets + ((-1.0, 1.0) if (x0 < 0 or x1 > 1) and p.offsets == (0.0,) else ()):
                if bx1 + off < x0 or bx0 + off > x1:
                    continue
                shift = np.array([off, 0.0])
                ext = _px16(project(p.ext + shift, cam, w, h))
                if fill is not None:
                    cv2.fillPoly(img, [ext], fill, lineType=cv2.LINE_AA, shift=4)
                    for hole in p.holes:
                        cv2.fillPoly(img, [_px16(project(hole + shift, cam, w, h))], default_fill,
                                     lineType=cv2.LINE_AA, shift=4)
                if oc is not None:
                    cv2.polylines(img, [ext], True, oc, line_w, lineType=cv2.LINE_AA, shift=4)


def draw_graticule(img: np.ndarray, cam, color) -> None:
    h, w = img.shape[:2]
    cx, cy, span = cam
    deg = span * 360.0
    step = next((s for s in (1, 2, 5, 10, 15, 30, 45, 90) if deg / s <= 9), 90)
    lon0, lon1 = cx * 360 - 180 - deg / 2, cx * 360 - 180 + deg / 2
    k = math.floor(lon0 / step) * step
    while k <= lon1 + step:
        x, _ = to_world(k, 0.0)
        sx = (float(x) - cx) * (w / span) + w / 2
        cv2.line(img, (int(sx * 16), 0), (int(sx * 16), h * 16), color, 1, cv2.LINE_AA, 4)
        k += step
    _, ytop = cx, cy - span * h / w / 2
    _, ybot = cx, cy + span * h / w / 2
    _, lat_top = world_to_lonlat(0, max(0.0, ytop))
    _, lat_bot = world_to_lonlat(0, min(1.0, ybot))
    k = math.floor(lat_bot / step) * step
    while k <= lat_top + step:
        _, y = to_world(0.0, max(-MAX_LAT, min(MAX_LAT, k)))
        sy = (float(y) - cy) * (w / span) + h / 2
        cv2.line(img, (0, int(sy * 16)), (w * 16, int(sy * 16)), color, 1, cv2.LINE_AA, 4)
        k += step


def bezier_arc(a, b, bend: float = 0.22, n: int = 48) -> np.ndarray:
    a, b = np.array(a, float), np.array(b, float)
    mid = (a + b) / 2
    d = b - a
    nrm = np.array([-d[1], d[0]])
    ctrl = mid + nrm * bend
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 2 * a + 2 * (1 - t) * t * ctrl + t ** 2 * b


def polyline_partial(pts: np.ndarray, frac: float) -> tuple[np.ndarray, tuple[float, float], float]:
    """Parte de la polilínea hasta `frac` de su longitud. Devuelve (puntos, punta, ángulo)."""
    seg_len = np.hypot(*(np.diff(pts, axis=0)).T)
    cum = np.concatenate([[0], np.cumsum(seg_len)])
    total = cum[-1] if cum[-1] > 0 else 1e-9
    d = max(0.0, min(1.0, frac)) * total
    i = int(np.searchsorted(cum, d, side="right")) - 1
    i = max(0, min(i, len(pts) - 2))
    u = (d - cum[i]) / max(seg_len[i], 1e-12)
    tip = pts[i] + (pts[i + 1] - pts[i]) * u
    out = np.vstack([pts[: i + 1], tip[None]])
    ang = math.atan2(pts[i + 1][1] - pts[i][1], pts[i + 1][0] - pts[i][0])
    return out, (float(tip[0]), float(tip[1])), ang


def road_route(a, b, profile: str = "driving", n_max: int = 160):
    """Ruta real por caminos entre dos puntos del mundo (x,y) usando el servicio público OSRM (necesita internet).
    Devuelve puntos (N,2) en coordenadas del mundo, o None si no hay ruta/conexión. Se guarda en caché."""
    import hashlib, json, urllib.request
    from .core import CACHE_DIR
    lon1, lat1 = world_to_lonlat(*a)
    lon2, lat2 = world_to_lonlat(*b)
    key = hashlib.md5(f"{profile}{lon1:.4f},{lat1:.4f};{lon2:.4f},{lat2:.4f}".encode()).hexdigest()
    f = CACHE_DIR / "routes" / f"{key}.json"
    coords = None
    if f.exists():
        try:
            coords = json.loads(f.read_text("utf-8"))
        except Exception:
            coords = None
    if coords is None:
        url = (f"https://router.project-osrm.org/route/v1/{profile}/{lon1:.5f},{lat1:.5f};{lon2:.5f},{lat2:.5f}"
               "?overview=full&geometries=geojson")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VerticalStudio/2"})
            with urllib.request.urlopen(req, timeout=25) as r:
                data = json.loads(r.read().decode())
            coords = data["routes"][0]["geometry"]["coordinates"]
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(coords), "utf-8")
        except Exception:
            return None
    if len(coords) < 2:
        return None
    arr = np.array(coords, float)
    if len(arr) > n_max:
        arr = arr[np.linspace(0, len(arr) - 1, n_max).astype(int)]
    x, y = to_world(arr[:, 0], arr[:, 1])
    return np.column_stack([x, y])
