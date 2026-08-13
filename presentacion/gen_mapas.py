"""Genera los mapas SVG inline para las paginas de pitch de Modulo A, B y C.

La CSP de los artifacts bloquea cualquier host externo -- no hay tile server ni
MapLibre por CDN. El mapa se dibuja entero desde los datos del repo: silueta de
la ciudad a partir de los 48 poligonos de barrios (incluye la costa real del
Rio de la Plata), red vial completa del grafo de OSM (37.036 tramos, con la
geometria curva real donde existe), y encima las capas de datos.

Lee las páginas fuente de `paginas/` —que tienen los marcadores vacíos— y
escribe las versiones completas en `build/`, que es lo que se publica. La
separación importa: el mapa son ~1,5MB de paths por página, contenido derivado
que no tiene por qué vivir en el control de versiones. `build/` está en el
.gitignore.

Uso: python presentacion/gen_mapas.py
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import osmnx as ox
import pandas as pd
from shapely.geometry import LineString
from shapely.ops import unary_union
from shapely import wkt

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
FUENTE = AQUI / "paginas"
BUILD = AQUI / "build"
DATOS = RAIZ / "dashboard" / "public" / "data"
PROCESSED = RAIZ / "data" / "processed"
GRAFO = RAIZ / "data" / "features" / "grafo_vial.graphml"

W = 1000
PAD = 8

# jerarquia OSM -> capa de dibujo. El orden importa: las menores se dibujan
# primero y las troncales encima, como en cualquier mapa vial.
CAPAS_VIA = {
    "menor": {"residential", "living_street", "unclassified", "tertiary",
              "tertiary_link", "busway", "disused"},
    "media": {"secondary", "primary", "secondary_link", "primary_link"},
    "troncal": {"motorway", "trunk", "motorway_link", "trunk_link"},
}
# tolerancia de simplificacion en grados (~1e-5 grados = ~1,1m en latitud)
TOLERANCIA = {"menor": 8e-5, "media": 5e-5, "troncal": 3e-5}


def mercator(lon: float, lat: float) -> tuple[float, float]:
    return math.radians(lon), math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


class Proyeccion:
    """Web Mercator ajustada al bounding box de los barrios (la extension real
    de la ciudad, no la de la grilla de hexagonos) y con la altura del lienzo
    derivada de la relacion de aspecto, para no dejar franjas vacias."""

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


def anillo_a_d(coords, proy) -> str:
    pts = [proy(lo, la) for lo, la in coords]
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"


def poligono_a_d(geom, proy) -> str:
    partes = []
    polis = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    for p in polis:
        partes.append(anillo_a_d(p.exterior.coords, proy))
        for interior in p.interiors:
            partes.append(anillo_a_d(interior.coords, proy))
    return " ".join(partes)


def linea_a_d(geom, proy) -> str:
    pts = [proy(lo, la) for lo, la in geom.coords]
    # descarta puntos que caen a menos de medio pixel del anterior: a esta
    # escala no aportan nada y son la mitad del peso del archivo
    salida = [pts[0]]
    for x, y in pts[1:]:
        px, py = salida[-1]
        if abs(x - px) > 0.5 or abs(y - py) > 0.5:
            salida.append((x, y))
    if len(salida) < 2:
        return ""
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in salida)


def esc(t) -> str:
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def cuantiles(valores, n):
    orden = sorted(valores)
    return [orden[int(round(q * (len(orden) - 1)))] for q in [i / n for i in range(1, n)]]


def bin_de(valor, cortes):
    for i, c in enumerate(cortes):
        if valor <= c:
            return i
    return len(cortes)


class Base:
    """Silueta de la ciudad + red vial. Se calcula una vez y se reusa en los
    tres mapas: es lo caro (37k tramos) y no depende de la capa de datos."""

    def __init__(self):
        barrios = pd.read_parquet(PROCESSED / "barrios.parquet")
        self.geoms = [wkt.loads(w) for w in barrios["geometry_wkt"]]
        self.nombres = list(barrios["nombre"])
        self.proy = Proyeccion(self.geoms)
        self.tierra = unary_union(self.geoms)

        print("cargando grafo vial...", flush=True)
        G = ox.io.load_graphml(GRAFO)
        self.vias = {k: [] for k in CAPAS_VIA}
        for u, v, d in G.edges(data=True):
            h = d.get("highway")
            h = h[0] if isinstance(h, list) else h
            capa = next((k for k, s in CAPAS_VIA.items() if h in s), "menor")
            geom = d.get("geometry")
            if geom is None:
                geom = LineString([(G.nodes[u]["x"], G.nodes[u]["y"]),
                                   (G.nodes[v]["x"], G.nodes[v]["y"])])
            self.vias[capa].append(geom.simplify(TOLERANCIA[capa]))
        print({k: len(v) for k, v in self.vias.items()}, flush=True)

    def svg_base(self) -> list[str]:
        d_tierra = poligono_a_d(self.tierra, self.proy)
        # el clip a la silueta evita que los hexagonos se derramen sobre el rio
        p = [f'<defs><clipPath id="clip-tierra" clipPathUnits="userSpaceOnUse">'
             f'<path d="{d_tierra}" fill-rule="evenodd" /></clipPath></defs>',
             f'<rect class="agua" x="0" y="0" width="{W}" height="{self.proy.H}" />',
             f'<path class="tierra" d="{d_tierra}" fill-rule="evenodd" />']
        for capa in ("menor", "media", "troncal"):
            ds = [linea_a_d(g, self.proy) for g in self.vias[capa]]
            d = " ".join(x for x in ds if x)
            p.append(f'<path id="via-{capa}" class="via v-{capa}" d="{d}" />')
        contornos = " ".join(poligono_a_d(g, self.proy) for g in self.geoms)
        p.append(f'<path id="barrios" class="barrio-linea" d="{contornos}" fill-rule="evenodd" />')
        return p

    @staticmethod
    def svg_vias_encima() -> list[str]:
        """Redibuja avenidas y autopistas SOBRE la capa termica, referenciando
        los mismos paths con <use> (no duplica geometria, no pesa). Sin esto la
        mancha de riesgo tapa la trama vial y el mapa vuelve a ser un diagrama."""
        return ['<use href="#via-media" opacity="0.8" />',
                '<use href="#via-troncal" opacity="0.95" />',
                '<use href="#barrios" opacity="0.9" />']


def construir_mapa(base: Base, campo: str, etiqueta: str, capas: list[dict],
                   destacados: set | None = None, etiqueta_destacados: str = "") -> str:
    hexes = json.loads((DATOS / "hex_riesgo.geojson").read_text(encoding="utf-8"))["features"]
    destacados = destacados or set()

    if campo == "promedio":
        def valor(f):
            p = f["properties"]
            return (p["riesgo_manana"] + p["riesgo_tarde"] + p["riesgo_noche"] + p["riesgo_madrugada"]) / 4
    else:
        def valor(f):
            return f["properties"][campo]

    cortes = cuantiles([valor(f) for f in hexes], 5)
    proy = base.proy

    partes = [f'<svg viewBox="0 0 {W} {proy.H}" class="mapa" role="img" '
              f'aria-label="Mapa de la Ciudad de Buenos Aires con su red de calles: '
              f'{esc(etiqueta)} por hexágono en cinco niveles, del más bajo al más alto.">']
    partes += base.svg_base()

    # el riesgo va SOBRE la trama de calles, semitransparente, para que la
    # ciudad siga leyendose debajo -- es lo que lo hace un mapa y no un diagrama
    partes.append('<g class="capa-hex" clip-path="url(#clip-tierra)">')
    for f in hexes:
        p = f["properties"]
        v = valor(f)
        pts = f["geometry"]["coordinates"][0]
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in (proy(lo, la) for lo, la in pts)) + " Z"
        partes.append(
            f'<path class="hx b{bin_de(v, cortes)}" d="{d}"><title>{esc(p.get("barrio"))} — '
            f'{esc(etiqueta.lower())} {v:.3f}</title></path>'
        )
    partes.append("</g>")
    partes += base.svg_vias_encima()

    if destacados:
        partes.append('<g class="capa-corredor">')
        for f in hexes:
            if f["properties"]["hex_id"] not in destacados:
                continue
            pts = f["geometry"]["coordinates"][0]
            d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in (proy(lo, la) for lo, la in pts)) + " Z"
            partes.append(f'<path class="corr" d="{d}"><title>Hexágono de corredor</title></path>')
        partes.append("</g>")

    for capa in capas:
        partes.append(f'<g class="capa-pt {capa["clase"]}">')
        for pt in capa["puntos"]:
            x, y = proy(pt["lon"], pt["lat"])
            r = pt.get("r", capa["r"])
            partes.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}">'
                          f'<title>{esc(pt.get("titulo", capa["nombre"]))}</title></circle>')
        partes.append("</g>")

    partes.append("</svg>")

    ley = ['<div class="mapa-leyenda">',
           f'<span class="ml-item"><span class="ml-titulo">{esc(etiqueta)}</span></span>',
           '<span class="ml-ramp"><span class="ml-cap">bajo</span>']
    for i in range(5):
        ley.append(f'<span class="ml-sw b{i}"></span>')
    ley.append('<span class="ml-cap">alto</span></span>')
    if destacados:
        ley.append(f'<span class="ml-item"><span class="ml-dot c-corredor"></span>{esc(etiqueta_destacados)}</span>')
    for capa in capas:
        ley.append(f'<span class="ml-item"><span class="ml-dot {capa["clase"]}"></span>{esc(capa["nombre"])}</span>')
    ley.append('<span class="ml-item ml-nota">Calles y autopistas: red vial real (OpenStreetMap)</span>')
    ley.append("</div>")

    return "\n".join(partes) + "\n" + "\n".join(ley)


def puntos_de(archivo: str, titulo="") -> list[dict]:
    datos = json.loads((DATOS / archivo).read_text(encoding="utf-8"))
    if isinstance(datos, dict) and datos.get("type") == "FeatureCollection":
        return [{"lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1],
                 "titulo": titulo} for f in datos["features"]]
    return [{"lon": d["lon"], "lat": d["lat"],
             "titulo": f'#{d["ranking"]} — {titulo}' if d.get("ranking") else titulo}
            for d in datos]


def inyectar(nombre: str, contenido: str) -> None:
    """Lee de paginas/, escribe en build/ — la fuente nunca se toca."""
    txt = (FUENTE / nombre).read_text(encoding="utf-8")
    patron = re.compile("(<!--MAPA:START-->).*?(<!--MAPA:END-->)", re.DOTALL)
    if not patron.search(txt):
        raise SystemExit(f"no encontré los marcadores en {nombre}")
    BUILD.mkdir(exist_ok=True)
    (BUILD / nombre).write_text(
        patron.sub(lambda m: m.group(1) + "\n" + contenido + "\n" + m.group(2), txt),
        encoding="utf-8")
    print(f"{nombre}: mapa de {len(contenido):,} chars -> build/{nombre}")


def main() -> None:
    base = Base()
    print(f"lienzo {W}x{base.proy.H}")

    inyectar("modulo-a-patrullas.html", construir_mapa(
        base, "riesgo_tarde", "Riesgo del turno Tarde",
        [{"clase": "c-existente", "nombre": "Comisarías actuales (75)", "r": 3.5,
          "puntos": puntos_de("comisarias.geojson", "Comisaría existente")},
         {"clase": "c-propuesto", "nombre": "Patrullas propuestas (K=75)", "r": 5.5,
          "puntos": puntos_de("modulo_a_k75.json", "Patrulla propuesta")}]))

    inyectar("modulo-b-camaras.html", construir_mapa(
        base, "promedio", "Riesgo promedio de los 4 turnos",
        [{"clase": "c-existente", "nombre": "Cámaras existentes (224)", "r": 3,
          "puntos": puntos_de("camaras.geojson", "Cámara existente")},
         {"clase": "c-propuesto", "nombre": "Cámaras propuestas (30)", "r": 5,
          "puntos": puntos_de("modulo_b_red.json", "cámara propuesta")[:30]}]))

    accesos = json.loads((DATOS / "modulo_c.json").read_text(encoding="utf-8"))
    puntos_c = [{
        "lon": a["lon"], "lat": a["lat"],
        "r": round(10 - (a["ranking"] - 1) * 0.6, 1),
        "titulo": f'#{a["ranking"]} {a["nombre"]} — {a["accidentalidad_por_hex"]:.0f} siniestros/hex, '
                  f'riesgo {a["riesgo_delictivo_corredor"]:.2f}',
    } for a in accesos]
    inyectar("modulo-c-controles.html", construir_mapa(
        base, "promedio", "Riesgo promedio de los 4 turnos",
        [{"clase": "c-propuesto", "nombre": "Accesos rankeados (9, tamaño = puesto)", "r": 6,
          "puntos": puntos_c}],
        destacados={h for a in accesos for h in a["hexes_corredor"]},
        etiqueta_destacados="Hexágonos de corredor"))


if __name__ == "__main__":
    main()
