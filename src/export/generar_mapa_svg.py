"""
Genera `dashboard/public/data/mapa_base.json`: la geometría del mapa ya
proyectada a coordenadas SVG, lista para que el dashboard la dibuje sin
WebGL, sin workers y sin tiles.

POR QUÉ NO MAPLIBRE
En la máquina de desarrollo MapLibre no dibuja ninguna capa vectorial:
su worker se instancia pero devuelve CERO features para cualquier fuente
GeoJSON. Reproducido en una página HTML plana, sin bundler, con MapLibre
por <script> y dos fuentes -- los 401 hexágonos reales y un triángulo de
tres puntos escrito a mano: ambas dan 0. El raster del basemap sí anda,
porque no pasa por el worker. Aparte, el proceso GPU de Chrome se cae con
violación de acceso al compilar los shaders de MapLibre en esa GPU.

Dibujar el mapa como SVG esquiva las dos cosas de raíz: no hay worker que
pueda quedar mudo ni shaders que compilar. La geometría es la misma que ya
se usa en el material de presentación de los Módulos A, B y C.

Salida (un solo JSON):
  - proyeccion: parámetros para que el cliente proyecte cualquier lon/lat
  - tierra / barrios / vias: paths SVG del fondo (silueta real de CABA con
    su costa, y la red vial de OSM en tres jerarquías)
  - hex: un path por hexágono, con su id, barrio, comuna y riesgo por turno

Uso: python generar_mapa_svg.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import osmnx as ox
import pandas as pd
from shapely.geometry import LineString
from shapely.ops import unary_union
from shapely import wkt

RAIZ = Path(__file__).resolve().parent.parent.parent
PROCESSED = RAIZ / "data" / "processed"
FEATURES = RAIZ / "data" / "features"
SALIDA = RAIZ / "dashboard" / "public" / "data" / "mapa_base.json"
HEX_GEOJSON = RAIZ / "dashboard" / "public" / "data" / "hex_riesgo.geojson"

W = 1000
PAD = 8

CAPAS_VIA = {
    "menor": {"residential", "living_street", "unclassified", "tertiary",
              "tertiary_link", "busway", "disused"},
    "media": {"secondary", "primary", "secondary_link", "primary_link"},
    "troncal": {"motorway", "trunk", "motorway_link", "trunk_link"},
}
# las secundarias se simplifican más fuerte: son el 78% de los tramos y a
# esta escala su detalle fino no se ve, pero pesa en el JSON que baja el
# navegador
TOLERANCIA = {"menor": 1.2e-4, "media": 6e-5, "troncal": 3e-5}


def mercator(lon: float, lat: float) -> tuple[float, float]:
    return math.radians(lon), math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


class Proyeccion:
    def __init__(self, geoms):
        xs, ys = [], []
        for g in geoms:
            x0, y0, x1, y1 = g.bounds
            for lo, la in ((x0, y0), (x1, y1)):
                mx, my = mercator(lo, la)
                xs.append(mx)
                ys.append(my)
        self.x0, self.x1 = min(xs), max(xs)
        self.y0, self.y1 = min(ys), max(ys)
        self.esc = (W - 2 * PAD) / (self.x1 - self.x0)
        self.H = round((self.y1 - self.y0) * self.esc + 2 * PAD)

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        x, y = mercator(lon, lat)
        return (x - self.x0) * self.esc + PAD, (self.y1 - y) * self.esc + PAD

    def como_dict(self) -> dict:
        return {"x0": self.x0, "y1": self.y1, "esc": self.esc, "pad": PAD, "w": W, "h": self.H}


def anillo(coords, proy) -> str:
    pts = [proy(lo, la) for lo, la in coords]
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"


def poligono(geom, proy) -> str:
    partes = []
    for p in (geom.geoms if geom.geom_type == "MultiPolygon" else [geom]):
        partes.append(anillo(p.exterior.coords, proy))
        partes.extend(anillo(i.coords, proy) for i in p.interiors)
    return " ".join(partes)


def linea(geom, proy) -> str:
    pts = [proy(lo, la) for lo, la in geom.coords]
    salida = [pts[0]]
    for x, y in pts[1:]:
        px, py = salida[-1]
        if abs(x - px) > 0.5 or abs(y - py) > 0.5:
            salida.append((x, y))
    if len(salida) < 2:
        return ""
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in salida)


def main() -> None:
    barrios = pd.read_parquet(PROCESSED / "barrios.parquet")
    geoms = [wkt.loads(w) for w in barrios["geometry_wkt"]]
    proy = Proyeccion(geoms)
    print(f"lienzo {W}x{proy.H} — {len(geoms)} barrios")

    print("cargando grafo vial...")
    G = ox.io.load_graphml(FEATURES / "grafo_vial.graphml")
    vias: dict[str, list[str]] = {k: [] for k in CAPAS_VIA}
    for u, v, d in G.edges(data=True):
        h = d.get("highway")
        h = h[0] if isinstance(h, list) else h
        capa = next((k for k, s in CAPAS_VIA.items() if h in s), "menor")
        geom = d.get("geometry") or LineString(
            [(G.nodes[u]["x"], G.nodes[u]["y"]), (G.nodes[v]["x"], G.nodes[v]["y"])]
        )
        trazo = linea(geom.simplify(TOLERANCIA[capa]), proy)
        if trazo:
            vias[capa].append(trazo)
    print({k: len(v) for k, v in vias.items()})

    hexes = json.loads(HEX_GEOJSON.read_text(encoding="utf-8"))["features"]
    hex_out = []
    for f in hexes:
        p = f["properties"]
        hex_out.append({
            "id": p["hex_id"],
            "d": anillo(f["geometry"]["coordinates"][0], proy),
            "barrio": p.get("barrio"),
            "comuna": p.get("comuna"),
            "manana": p["riesgo_manana"], "tarde": p["riesgo_tarde"],
            "noche": p["riesgo_noche"], "madrugada": p["riesgo_madrugada"],
        })

    salida = {
        "proyeccion": proy.como_dict(),
        "tierra": poligono(unary_union(geoms), proy),
        "barrios": " ".join(poligono(g, proy) for g in geoms),
        "vias": {k: " ".join(v) for k, v in vias.items()},
        "hex": hex_out,
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"guardado {SALIDA} ({SALIDA.stat().st_size / 1e6:.2f} MB, {len(hex_out)} hexágonos)")


if __name__ == "__main__":
    main()
