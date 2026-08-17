"""
Capa base de la vista 3D: agua, verde, calles y puentes.

POR QUÉ EXISTE
`ingest_tejido_urbano.py` trae los volúmenes construidos, que es la mitad de la
ciudad. La otra mitad es el vacío: el río, los parques, la traza de las calles y
las autopistas elevadas. Sin eso el tejido flota en negro y no se reconoce nada
— la costa del Río de la Plata y la General Paz son, literalmente, la silueta
de Buenos Aires.

DE DÓNDE SALE CADA COSA
- **calles** y **espacios verdes**: de los parquet que el proyecto ya ingesta.
  `calles` trae `tipo_via` y `jerarquia`, que es lo que permite dibujar una
  jerarquía visual creíble (una autopista no se dibuja igual que un pasaje).
- **agua** y **puentes**: de OpenStreetMap, porque no están en los datos de la
  Ciudad. El río hay que recortarlo sí o sí: el polígono del Río de la Plata
  mide 30.256 km², unas 1.500 veces la superficie de CABA, y sin recorte pesa
  más que todo el resto junto.

FORMATOS, Y POR QUÉ NO TODO IGUAL
Las calles van a PMTiles (31.961 tramos, se piden por rango según el encuadre).
El agua y el verde van a GeoJSON plano: son pocos polígonos, se ven en todos los
zooms y teselarlos sería complicar sin ganar nada.

Uso: python build_base_3d.py
"""

from __future__ import annotations

import json
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import geopandas as gpd
import osmnx as ox
import pandas as pd
from shapely import wkt as _wkt
from shapely.geometry import box

RAIZ = Path(__file__).resolve().parent.parent
PROC = RAIZ / "data" / "processed"
DESTINO = RAIZ / "dashboard" / "public" / "tejido"

# Caja de recorte: CABA más un margen hacia el río y la provincia, para que al
# alejarse la costa siga llenando el encuadre en vez de cortarse en seco.
OESTE, SUR, ESTE, NORTE = -58.58, -34.74, -58.25, -34.48

# Caché de osmnx apuntado a una ruta fija del proyecto (la que ya ignora git).
# Por defecto osmnx cachea en ./cache relativo al directorio de trabajo, así que
# la misma consulta desde dos lugares distintos se baja dos veces — y Overpass
# corta por límite de uso. Con esto, reintentar no vuelve a pedirle nada.
ox.settings.cache_folder = str(RAIZ / "src" / "etl" / "cache")
ox.settings.use_cache = True
# 60 s y no más: con varios espejos conviene descartar rápido el que no
# contesta. Con 300 s, un servidor caído bloquea cinco minutos antes de pasar al
# siguiente y la corrida entera se va a un cuarto de hora de espera pura.
ox.settings.requests_timeout = 60

CRS_METRICO = 5347      # POSGAR 2007 faja 5, para simplificar en metros
TOLERANCIA_M = 3.0      # simplificación: 3 m no se nota y achica mucho

# Jerarquía visual. Sale de cruzar `tipo_via` con `jerarquia`: el tipo dice qué
# es la vía y la jerarquía cuánto pesa en la red, y para dibujar hace falta un
# solo número ordenado.
def clase_de_calle(tipo: str, jerarquia: str) -> str:
    t, j = (tipo or "").upper(), (jerarquia or "").upper()
    if "AUTOPISTA" in t:
        return "autopista"
    if t in ("AVENIDA", "BOULEVARD") or "TRONCAL" in j:
        return "avenida"
    if "DISTRIBUIDORA" in j:
        return "secundaria"
    if "PEATONAL" in t:
        return "peatonal"
    return "calle"


"""Espejos de Overpass, en orden.

El servidor principal se cayó tres veces seguidas mientras se armaba esta capa
(timeout de conexión a los 300 s), y sin él no hay agua, puentes ni monumentos.
Los espejos sirven la misma base de OSM, así que rotar es transparente.
"""
ESPEJOS_OVERPASS = [
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.osm.jp/api",
]


def consultar_osm(tags: dict) -> gpd.GeoDataFrame:
    """Consulta OSM probando los espejos hasta que uno conteste."""
    ultimo: Exception | None = None
    for url in ESPEJOS_OVERPASS:
        ox.settings.overpass_url = url
        try:
            return ox.features.features_from_bbox((OESTE, SUR, ESTE, NORTE), tags=tags)
        except Exception as e:                       # timeout, 429, 504...
            ultimo = e
            print(f"    {url.split('//')[1].split('/')[0]} no respondió "
                  f"({type(e).__name__}), probando el siguiente...")
    raise RuntimeError(f"ningún espejo de Overpass respondió: {ultimo}")


def leer_wkt(nombre: str) -> gpd.GeoDataFrame:
    d = pd.read_parquet(PROC / f"{nombre}.parquet")
    return gpd.GeoDataFrame(d.drop(columns="geometry_wkt"),
                            geometry=d["geometry_wkt"].map(_wkt.loads), crs=4326)


def simplificar(g: gpd.GeoDataFrame, tol: float = TOLERANCIA_M) -> gpd.GeoDataFrame:
    """Simplifica en metros. En grados la tolerancia no significa nada: 0,001°
    son 111 m en latitud pero 91 m en longitud a esta latitud."""
    g = g.copy()
    g["geometry"] = g.to_crs(CRS_METRICO).geometry.simplify(tol).to_crs(4326)
    return g[~g.geometry.is_empty & g.geometry.notna()]


def escribir_geojson(g: gpd.GeoDataFrame, destino: Path, columnas: list[str]) -> None:
    """GeoJSON con coordenadas a 6 decimales (~11 cm), que es de lejos lo que
    más pesa en un GeoJSON de polígonos."""
    d = json.loads(g[columnas + ["geometry"]].to_json(drop_id=True))

    def redondear(o):
        if isinstance(o, list):
            return [redondear(x) for x in o]
        return round(o, 6) if isinstance(o, float) else o

    for f in d["features"]:
        f["geometry"]["coordinates"] = redondear(f["geometry"]["coordinates"])
    destino.write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
    print(f"    {destino.name}: {len(d['features']):,} features, "
          f"{destino.stat().st_size / 1048576:.2f} MB")


# ────────────────────────────────────────────────────────────────────── capas

def agua() -> None:
    print("[1] agua (OSM)...")
    caja = box(OESTE, SUR, ESTE, NORTE)
    g = consultar_osm({"natural": ["water"], "waterway": ["riverbank", "dock"],
                       "landuse": ["reservoir"]})
    g = g[g.geom_type.isin(["Polygon", "MultiPolygon"])].to_crs(4326)
    # el polígono del Río de la Plata entra entero aunque se pida por caja
    g["geometry"] = g.geometry.intersection(caja)
    g = g[~g.geometry.is_empty & g.geometry.notna()].reset_index(drop=True)
    g["nombre"] = g.get("name", pd.Series(index=g.index, dtype=object)).fillna("")
    escribir_geojson(simplificar(g, 6.0), DESTINO / "agua.geojson", ["nombre"])


def verde() -> None:
    print("[2] espacios verdes...")
    g = leer_wkt("espacios_verdes")
    g = g[g.geom_type.isin(["Polygon", "MultiPolygon"])]
    # los canteros centrales de las avenidas son ruido a esta escala: son miles
    # de tiras de dos metros que ensucian el dibujo y no leen como verde
    antes = len(g)
    g = g[(g["clasificac"] != "CANTERO CENTRAL") & (g["area"] >= 500)]
    print(f"    sin canteros y <500 m²: {antes:,} -> {len(g):,}")
    g["clase"] = g["clasificac"].str.title()
    escribir_geojson(simplificar(g), DESTINO / "verde.geojson", ["nombre", "clase"])


def puentes() -> None:
    print("[3] puentes y vías elevadas (OSM)...")
    g = consultar_osm({"bridge": True})
    g = g[g.geom_type.isin(["LineString", "MultiLineString"])].reset_index(drop=True)
    hw = g.get("highway", pd.Series(index=g.index, dtype=object)).astype(str)
    rw = g.get("railway", pd.Series(index=g.index, dtype=object)).astype(str)
    # solo lo que se lee a escala urbana: autopistas elevadas y ferrocarril.
    # Las pasarelas peatonales son 435 líneas de veinte metros que no aportan.
    g["clase"] = "otro"
    g.loc[hw.str.startswith(("motorway", "trunk", "primary")), "clase"] = "autopista"
    g.loc[rw.isin(["rail", "light_rail"]), "clase"] = "tren"
    g = g[g["clase"] != "otro"]
    g["nombre"] = g.get("name", pd.Series(index=g.index, dtype=object)).fillna("")
    print(f"    {len(g):,} tramos ({g['clase'].value_counts().to_dict()})")
    escribir_geojson(simplificar(g), DESTINO / "puentes.geojson", ["nombre", "clase"])


"""Alturas que OSM no declara, completadas a mano.

Se completan solo las que faltan y son reconocibles a simple vista: si el
monumento más visible de la Ciudad no está, la vista pierde credibilidad
entera. Cada valor es la altura publicada del monumento, no una estimación.
Todo lo demás sale de la etiqueta `height` de OSM o de los pisos declarados.
"""
ALTURAS_A_MANO = {
    "Obelisco": 67.5,     # altura oficial del monumento (1936)
}
ALTURA_POR_DEFECTO = 12.0    # monumento sin altura conocida ni pisos


def monumentos() -> None:
    """Monumentos y estructuras que el Tejido Urbano no tiene.

    Hace falta porque el Tejido Urbano es **edificación por parcela**, y lo que
    está parado en el medio de una plaza no ocupa parcela: el Obelisco no
    aparece por ningún lado. Se verificó — no hay ningún volumen de entre 55 y
    80 m a menos de 130 m de sus coordenadas, y lo más alto cerca es un
    edificio de 48,9 m del otro lado de la 9 de Julio.

    Se descarta lo que ya está en el tejido (el Teatro Colón sí ocupa parcela,
    así que traerlo de OSM lo dibujaría dos veces, una encima de la otra).
    """
    print("[5] monumentos (OSM)...")
    g = consultar_osm(
        {"man_made": ["obelisk", "tower", "monument", "lighthouse", "water_tower"],
         "historic": ["monument", "memorial"], "tourism": ["attraction"]})
    g = g[g.geom_type.isin(["Polygon", "MultiPolygon"])].reset_index(drop=True)
    g["nombre"] = g.get("name", pd.Series(index=g.index, dtype=object)).fillna("")

    alt = pd.to_numeric(
        g.get("height", pd.Series(index=g.index, dtype=object))
        .astype(str).str.replace(" m", "", regex=False), errors="coerce")
    pisos = pd.to_numeric(g.get("building:levels", pd.Series(index=g.index, dtype=object)),
                          errors="coerce")
    alt = alt.fillna(pisos * 2.8)
    alt = alt.fillna(g["nombre"].map(ALTURAS_A_MANO))
    g["altura"] = alt.fillna(ALTURA_POR_DEFECTO).round(1)

    # fuera lo que el tejido ya tiene: se compara el centroide contra los
    # volúmenes reales usando el índice espacial, que si no son 117 × 1.019.395
    tejido = gpd.read_parquet(RAIZ / "data" / "processed" / "tejido_urbano.parquet")
    centros = gpd.GeoDataFrame(geometry=g.geometry.centroid, crs=g.crs)
    ya_esta = gpd.sjoin(centros, tejido[["geometry"]], predicate="within", how="left")
    duplicados = ya_esta.index_right.notna().groupby(level=0).any()
    antes = len(g)
    g = g[~g.index.map(duplicados).fillna(False)]
    print(f"    {antes} monumentos, {antes - len(g)} ya estaban en el tejido "
          f"-> quedan {len(g)}")
    if len(g):
        top = g.nlargest(6, "altura")[["nombre", "altura"]]
        print("    más altos:", dict(zip(top["nombre"], top["altura"])))
    escribir_geojson(simplificar(g, 1.0), DESTINO / "monumentos.geojson",
                     ["nombre", "altura"])


def calles() -> None:
    print("[4] calles...")
    g = leer_wkt("calles")
    g["clase"] = [clase_de_calle(t, j) for t, j in zip(g["tipo_via"], g["jerarquia"])]
    print(f"    {len(g):,} tramos ({g['clase'].value_counts().to_dict()})")
    g = simplificar(g, 2.0)

    destino = DESTINO / "calles.pmtiles"
    for resto in (destino, Path(f"{destino}.tmp.mbtiles"),
                  Path(f"{destino}.tmp.mbtiles.temp.db")):
        resto.unlink(missing_ok=True)
    t0 = time.time()
    g[["clase", "nombre", "geometry"]].to_file(
        destino, driver="PMTiles", layer="calles", MINZOOM=11, MAXZOOM=16)
    print(f"    {destino.name}: {destino.stat().st_size / 1048576:.2f} MB "
          f"en {time.time() - t0:.0f}s")


def arbolado() -> None:
    """Copas de árbol como volúmenes, a partir del censo de la Ciudad.

    350.660 ejemplares con altura medida. Se dibuja **solo la copa**, no el
    tronco: a la escala en que se mira la ciudad el tronco no llega a un píxel,
    y duplicar la geometría para algo invisible costaría el doble de teselas.
    La copa es un prisma que arranca al 45% de la altura del árbol, que es
    donde empieza la fronda de un árbol de vereda podado.

    **El radio de copa NO está en el dataset y es una aproximación de dibujo.**
    El censo mide altura y diámetro de tronco a la altura del pecho, no la
    extensión de la copa. Se deriva del tronco, que es la relación menos mala
    (un árbol más grueso tiene copa más ancha), acotada a un rango razonable
    para vereda. Sirve para que el arbolado se vea; no lo uses para calcular
    sombra ni cobertura vegetal.
    """
    print("[6] arbolado...")
    d = pd.read_parquet(RAIZ / "data" / "processed" / "arbolado.parquet")
    print(f"    {len(d):,} ejemplares")

    radio = (0.08 * d["dap_cm"]).clip(1.2, 6.0)
    # sin diámetro de tronco se cae a la altura, que es peor pero es lo que hay
    radio = radio.where(d["dap_cm"] > 0, (0.22 * d["altura_m"]).clip(1.2, 5.0))

    pts = gpd.GeoSeries(gpd.points_from_xy(d["lon"], d["lat"]), crs=4326).to_crs(CRS_METRICO)
    # resolution=2 da octógonos (geopandas lo traduce a quad_segs de shapely, y
    # pasar los dos choca): ocho vértices alcanzan y sobran para una copa de
    # cinco metros vista desde arriba, y pesan la mitad que un círculo
    copas = pts.buffer(radio.to_numpy(), resolution=2).to_crs(4326)

    g = gpd.GeoDataFrame({"alt": d["altura_m"].round(1)}, geometry=copas, crs=4326)
    destino = DESTINO / "arbolado.pmtiles"
    for resto in (destino, Path(f"{destino}.tmp.mbtiles"),
                  Path(f"{destino}.tmp.mbtiles.temp.db")):
        resto.unlink(missing_ok=True)
    t0 = time.time()
    # desde z15: una copa de 5 m a z14 mide medio píxel
    g.to_file(destino, driver="PMTiles", layer="arbolado", MINZOOM=15, MAXZOOM=16)
    print(f"    {destino.name}: {destino.stat().st_size / 1048576:.2f} MB "
          f"en {time.time() - t0:.0f}s")


def alumbrado() -> None:
    """Las luminarias de la Ciudad, para el aire nocturno.

    102.700 puntos que ya estaban ingestados. No llevan ningún atributo a la
    tesela: se dibujan todas igual, y lo único que importa es dónde están.
    """
    print("[7] alumbrado...")
    d = pd.read_parquet(RAIZ / "data" / "processed" / "alumbrado.parquet")
    d = d.dropna(subset=["lat", "lng"])
    g = gpd.GeoDataFrame(geometry=gpd.points_from_xy(d["lng"], d["lat"]), crs=4326)
    print(f"    {len(g):,} luminarias")

    destino = DESTINO / "alumbrado.pmtiles"
    for resto in (destino, Path(f"{destino}.tmp.mbtiles"),
                  Path(f"{destino}.tmp.mbtiles.temp.db")):
        resto.unlink(missing_ok=True)
    t0 = time.time()
    g.to_file(destino, driver="PMTiles", layer="alumbrado", MINZOOM=14, MAXZOOM=16)
    print(f"    {destino.name}: {destino.stat().st_size / 1048576:.2f} MB "
          f"en {time.time() - t0:.0f}s")


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    agua()
    verde()
    puentes()
    monumentos()
    calles()
    arbolado()
    alumbrado()
    print(f"\nListo. Todo en /{DESTINO.name}/")


if __name__ == "__main__":
    main()
