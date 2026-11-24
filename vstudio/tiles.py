"""Mapas reales: descarga de teselas XYZ (satélite, calles, oscuro…) con caché en disco y compositor Mercator."""
from __future__ import annotations

import math
import os
import threading
import time
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from .core import CACHE_DIR

UA = "VerticalStudio/1.1 (herramienta local de video; contacto: usuario)"

# Estilos incluidos. Revisa los términos de cada proveedor si monetizas tus videos; para uso comercial intensivo
# conviene usar tu propia llave (MapTiler, Mapbox, Stadia…) con el ajuste «map_tile_url».
PROVIDERS: dict[str, dict] = {
    "satelite": {"label": "Satélite", "ext": "jpg", "max": 19, "bg": (14, 18, 26),
                 "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                 "attr": "Imágenes © Esri, Maxar, Earthstar Geographics"},
    "natural": {"label": "Natural (relieve y fondo marino, NASA)", "ext": "jpg", "max": 8, "bg": (10, 30, 60),
                "url": "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg",
                "attr": "Imágenes: NASA Earth Observatory / GIBS"},
    "oscuro": {"label": "Oscuro (calles)", "ext": "png", "max": 20, "bg": (14, 16, 20),
               "url": "https://basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png",
               "attr": "© OpenStreetMap contributors © CARTO"},
    "claro": {"label": "Claro (calles)", "ext": "png", "max": 20, "bg": (212, 218, 222),
              "url": "https://basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png",
              "attr": "© OpenStreetMap contributors © CARTO"},
    "calles": {"label": "Calles (OpenStreetMap)", "ext": "png", "max": 19, "bg": (210, 214, 208),
               "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png", "attr": "© OpenStreetMap contributors"},
    "terreno": {"label": "Terreno y relieve", "ext": "jpg", "max": 18, "bg": (200, 206, 196),
                "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
                "attr": "© Esri, HERE, Garmin, OpenStreetMap contributors"},
}
STYLE_CHOICES = list(PROVIDERS.keys()) + ["personalizado", "vectorial"]


class TileSource:
    def __init__(self, style: str, custom_url: str | None = None, attr: str | None = None):
        if style == "personalizado" or custom_url and style not in PROVIDERS:
            self.name = "custom_" + format(abs(hash(custom_url or "")) % 10 ** 8, "08d")
            self.url = custom_url or ""
            self.ext = "png"
            self.max = 19
            self.bg = (16, 18, 22)
            self.attr = attr or ""
        else:
            p = PROVIDERS[style]
            self.name, self.url, self.ext, self.max, self.bg = style, p["url"], p["ext"], p["max"], p["bg"]
            self.attr = p["attr"]
        self.dir = CACHE_DIR / "tiles" / self.name
        # híbrido: «natural» (NASA, máx. z8) pasa a Esri satélite al acercarse mucho, para que no se pixele
        self.deep: "TileSource | None" = None
        self.deep_from = self.max + 1
        if style == "natural":
            self.deep = TileSource("satelite")
            self.deep_from = self.max + 1
            self.max = self.deep.max
            self.attr = self.attr + " · Esri, Maxar"
        self._mem: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self.failed: set = set()
        self.streak = 0
        self.offline_until = 0.0

    # ---- disco / red -----------------------------------------------------
    def _file(self, z: int, x: int, y: int) -> Path:
        return self.dir / str(z) / str(x) / f"{y}.{self.ext}"

    def _src(self, z: int) -> "TileSource":
        return self.deep if self.deep is not None and z >= self.deep_from else self

    def have(self, z: int, x: int, y: int) -> bool:
        if self._src(z) is not self:
            return self.deep.have(z, x, y)
        return self._file(z, x, y).exists()

    def fetch(self, z: int, x: int, y: int) -> bool:
        if self._src(z) is not self:
            return self.deep.fetch(z, x, y)
        f = self._file(z, x, y)
        if f.exists():
            return True
        if time.time() < self.offline_until:  # sin internet: falla rápido en vez de esperar timeouts
            self.failed.add((z, x, y))
            return False
        url = self.url.format(z=z, x=x, y=y, s="a")
        for attempt in range(2):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = r.read()
                if len(data) < 100:
                    raise OSError("tesela vacía")
                f.parent.mkdir(parents=True, exist_ok=True)
                tmp = f.with_suffix(f.suffix + ".part")
                tmp.write_bytes(data)
                os.replace(tmp, f)
                self.streak = 0
                return True
            except Exception:
                continue
        self.failed.add((z, x, y))
        self.streak += 1
        if self.streak >= 6:
            self.offline_until = time.time() + 40
        return False

    def prefetch(self, tiles, workers: int = 8, progress=None) -> tuple[int, int]:
        """Descarga en paralelo las teselas que falten. Devuelve (necesarias, fallidas)."""
        todo = [t for t in tiles if not self.have(*t)]
        if not todo:
            return len(tiles), 0
        done = 0
        bad = 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for ok in ex.map(lambda t: self.fetch(*t), todo):
                done += 1
                bad += 0 if ok else 1
                if progress and done % 4 == 0:
                    progress(done / len(todo))
        return len(tiles), bad

    # ---- lectura ---------------------------------------------------------
    def get(self, z: int, x: int, y: int) -> np.ndarray | None:
        if self._src(z) is not self:
            return self.deep.get(z, x, y)
        key = (z, x, y)
        with self._lock:
            if key in self._mem:
                self._mem.move_to_end(key)
                return self._mem[key]
        f = self._file(z, x, y)
        img = None
        if f.exists():
            arr = cv2.imdecode(np.frombuffer(f.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
            if arr is not None:
                img = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
                if img.shape[0] != 256 or img.shape[1] != 256:
                    img = cv2.resize(img, (256, 256), interpolation=cv2.INTER_AREA)
        with self._lock:
            self._mem[key] = img
            if len(self._mem) > 700:
                self._mem.popitem(last=False)
        return img

    # ---- geometría -------------------------------------------------------
    def zoom_for(self, span: float, w: int) -> int:
        z = math.ceil(math.log2(max(w / span / 256.0, 1e-9)))
        return int(max(0, min(self.max, z)))

    def tiles_for(self, cam, w: int, h: int) -> tuple[int, list[tuple[int, int, int]]]:
        cx, cy, span = cam
        z = self.zoom_for(span, w)
        n = 2 ** z
        half_h = span * h / w / 2
        tx0, tx1 = math.floor((cx - span / 2) * n), math.floor((cx + span / 2) * n)
        ty0 = math.floor(max(0.0, cy - half_h) * n)
        ty1 = math.floor(min(1.0 - 1e-9, cy + half_h) * n)
        out = []
        if cy + half_h < 0 or cy - half_h > 1:
            return z, out
        for ty in range(max(0, ty0), min(n - 1, ty1) + 1):
            for tx in range(tx0, tx1 + 1):
                out.append((z, tx % n, ty))
        return z, out

    def render(self, cam, w: int, h: int) -> np.ndarray:
        cx, cy, span = cam
        z = self.zoom_for(span, w)
        n = 2 ** z
        half_h = span * h / w / 2
        out = np.empty((h, w, 3), np.uint8)
        out[:] = self.bg
        if cy + half_h < 0 or cy - half_h > 1:
            return out
        tx0, tx1 = math.floor((cx - span / 2) * n), math.floor((cx + span / 2) * n)
        ty0 = max(0, math.floor(max(0.0, cy - half_h) * n))
        ty1 = min(n - 1, math.floor(min(1.0 - 1e-9, cy + half_h) * n))
        mw, mh = (tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256
        mosaic = np.empty((mh, mw, 3), np.uint8)
        mosaic[:] = self.bg
        for j, ty in enumerate(range(ty0, ty1 + 1)):
            for i, tx in enumerate(range(tx0, tx1 + 1)):
                t = self.get(z, tx % n, ty)
                if t is not None:
                    mosaic[j * 256:(j + 1) * 256, i * 256:(i + 1) * 256] = t
        s = w / span
        k = s / (256.0 * n)  # píxeles de pantalla por píxel de tesela
        bx = (tx0 / n - cx) * s + w / 2
        by = (ty0 / n - cy) * s + h / 2
        kx = ky = 1.0
        if k < 0.8:  # reducir con INTER_AREA antes de mover (evita aliasing)
            nw, nh = max(1, int(round(mw * k))), max(1, int(round(mh * k)))
            mosaic = cv2.resize(mosaic, (nw, nh), interpolation=cv2.INTER_AREA)
            kx, ky = nw / mw, nh / mh
        M = np.array([[k / kx, 0, bx], [0, k / ky, by]], np.float64)
        interp = cv2.INTER_CUBIC if k > 1.15 else cv2.INTER_LINEAR
        return cv2.warpAffine(mosaic, M, (w, h), out, flags=interp, borderMode=cv2.BORDER_TRANSPARENT)


_sources: dict = {}


def get_source(style: str, custom_url: str | None = None, attr: str | None = None) -> TileSource:
    key = (style, custom_url)
    if key not in _sources:
        _sources[key] = TileSource(style, custom_url, attr)
    return _sources[key]
