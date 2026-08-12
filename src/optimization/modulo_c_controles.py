"""
CAPA 2, Módulo C (arquitectura-sige-ba.pdf, sección 4.3): ranking de
accesos por autopista para ubicar controles/garitas, combinando
accidentalidad histórica (siniestros_hechos) + riesgo delictivo
(riesgo_predicho) del corredor que sale de cada acceso.

Actualización P1 (auditoría técnica externa, sección 7): la versión
anterior aproximaba el "corredor" con un buffer de radio fijo alrededor
de cada acceso, documentado explícitamente como simplificación porque
calles.parquet no tiene topología navegable. Con el grafo vial real de
OSM (`build_grafo_vial.py`) ya no hace falta esa aproximación: desde
cada acceso se recorre el grafo real restringido a vías importantes
(`highway` en motorway/trunk/primary/secondary — el análogo de OSM a
"troncal/distribuidora principal" de GCBA), vía Dijkstra de una sola
fuente con corte de distancia. El resultado es el corredor real que sale
de ese acceso, no un círculo que puede cruzar manzanas sin calle
troncal, ni cortar antes de una que sí lo es.

Dos correcciones sobre la primera versión con grafo real, encontradas al
preparar el material de presentación:

1. ACCESOS DUPLICADOS. La fuente trae 11 accesos, pero "Illia",
   "Pórtico Illia al Sur" (a 8 metros del anterior) y "Pórtico Illia al
   Norte" (a ~130m) son el mismo intercambiador: caían en el mismo nodo
   del grafo, producían corredores idénticos (381 siniestros, 5 hexágonos,
   33 nodos) y ocupaban tres de los once puestos del ranking, además de
   desplazar los percentiles del resto. Se colapsan los accesos que
   comparten nodo de entrada al grafo — quedan 9 corredores únicos.

2. SUMA CONTRA PROMEDIO. La accidentalidad del corredor se sumaba sobre
   sus hexágonos mientras el riesgo delictivo se promediaba. Como los
   corredores varían 7,3x en tamaño (3 a 22 hexágonos según qué tan lejos
   propague el subgrafo de vías importantes desde cada acceso), la suma
   premiaba al corredor grande por ser grande. Ahora las dos componentes
   son intensivas: siniestros POR HEXÁGONO contra riesgo promedio por
   hexágono. Como los hexágonos H3 tienen área casi idéntica, "por
   hexágono" es "por unidad de área".
   El total crudo se conserva en `accidentalidad_corredor` para poder
   auditar, pero el score usa la versión normalizada.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import h3
import networkx as nx
import osmnx as ox
import pandas as pd
from shapely import STRtree
from shapely.geometry import LineString
from shapely.ops import unary_union

PROCESSED = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
GRAFO_PATH = FEATURES / "grafo_vial.graphml"

CRS_GEO = "EPSG:4326"
CRS_METROS = "EPSG:5347"

RADIO_CORREDOR_M = 2000
# ancho a cada lado de la traza para contar un siniestro como "del corredor".
# 30m cubre el ancho de calzada más el error de geocodificación (los siniestros
# vienen geocodificados a la dirección, no al punto exacto del impacto).
BUFFER_TRAZA_M = 30
JERARQUIAS_OSM_IMPORTANTES = {"motorway", "trunk", "primary", "secondary",
                               "motorway_link", "trunk_link", "primary_link", "secondary_link"}
RESOLUCION_H3 = 8


def cargar_siniestros_puntos() -> tuple[STRtree, int]:
    """Siniestros como puntos proyectados a metros, para contarlos sobre la
    traza del corredor y no sobre todo el hexágono.

    Las coordenadas vienen como TEXTO y con basura ('#¡REF!' en 294 filas):
    se parsean con coerce y se descarta lo que no cae en el bbox de CABA.
    Quedan 62.787 de 63.081 (99,5%)."""
    d = pd.read_parquet(
        FEATURES / "siniestros_hechos_hex.parquet",
        columns=["latitud_siniestro", "longitud_siniestro"],
    )
    lat = pd.to_numeric(d["latitud_siniestro"], errors="coerce")
    lon = pd.to_numeric(d["longitud_siniestro"], errors="coerce")
    ok = lat.between(-34.75, -34.50) & lon.between(-58.55, -58.30)
    print(f"Siniestros con coordenada usable: {int(ok.sum()):,} de {len(d):,} ({ok.mean():.1%})")

    pts = gpd.GeoSeries(gpd.points_from_xy(lon[ok], lat[ok]), crs=CRS_GEO).to_crs(CRS_METROS)
    return STRtree(pts.to_numpy()), int(ok.sum())


def traza_del_corredor(subgrafo) -> tuple[object, float]:
    """Geometría del corredor en metros y su largo en km. Usa la geometría
    curva real del tramo donde OSM la trae; si no, la recta entre nodos."""
    geoms = []
    for u, v, d in subgrafo.edges(data=True):
        g = d.get("geometry")
        if g is None:
            g = LineString([(subgrafo.nodes[u]["x"], subgrafo.nodes[u]["y"]),
                            (subgrafo.nodes[v]["x"], subgrafo.nodes[v]["y"])])
        geoms.append(g)
    if not geoms:
        return None, 0.0
    traza = gpd.GeoSeries([unary_union(geoms)], crs=CRS_GEO).to_crs(CRS_METROS).iloc[0]
    return traza, traza.length / 1000


def es_via_importante(highway) -> bool:
    valores = highway if isinstance(highway, list) else [highway]
    return any(v in JERARQUIAS_OSM_IMPORTANTES for v in valores)


def main() -> None:
    accesos = pd.read_parquet(FEATURES / "accesos_autopistas_hex.parquet").dropna(subset=["lat", "lon"])

    print("Cargando grafo vial y construyendo subgrafo de vías importantes...")
    G = ox.io.load_graphml(GRAFO_PATH)
    edges_importantes = [(u, v, k) for u, v, k, d in G.edges(keys=True, data=True) if es_via_importante(d.get("highway"))]
    G_importante = G.edge_subgraph(edges_importantes).copy()
    print(f"Subgrafo importante: {G_importante.number_of_nodes():,} nodos, {G_importante.number_of_edges():,} tramos "
          f"(de {G.number_of_nodes():,}/{G.number_of_edges():,} totales)")

    nodo_acceso = ox.distance.nearest_nodes(
        G_importante, accesos["lon"].to_numpy(), accesos["lat"].to_numpy()
    )

    arbol_siniestros, _ = cargar_siniestros_puntos()

    siniestros = pd.read_parquet(FEATURES / "siniestros_hechos_hex.parquet")
    siniestros_por_hex = siniestros.groupby("hex_id", observed=True).size()

    riesgo = pd.read_parquet(FEATURES / "riesgo_predicho.parquet")
    riesgo_por_hex = riesgo.groupby("hex_id", observed=True)["score_riesgo"].mean()

    # accesos que caen en el mismo nodo del grafo son el mismo intercambiador
    # (ver docstring): se agrupan antes de recorrer, así el corredor se calcula
    # una vez y no ocupa varios puestos del ranking con la misma fila.
    accesos = accesos.reset_index(drop=True)
    accesos["nodo_grafo"] = nodo_acceso
    grupos = accesos.groupby("nodo_grafo", sort=False)
    n_dup = len(accesos) - grupos.ngroups
    if n_dup:
        print(f"Accesos que comparten nodo de entrada al grafo: {len(accesos)} filas -> {grupos.ngroups} corredores únicos")

    filas = []
    for nodo, grupo in grupos:
        acceso = {
            "nombre": " / ".join(sorted(grupo["nombre"])),
            "autopista": " / ".join(sorted(set(grupo["autopista"]))),
            # los agrupados están a metros entre sí (mismo nodo del grafo), así
            # que el promedio de sus coordenadas es representativo del punto
            "lat": float(grupo["lat"].mean()), "lon": float(grupo["lon"].mean()),
        }
        alcanzables = nx.single_source_dijkstra_path_length(G_importante, nodo, cutoff=RADIO_CORREDOR_M, weight="length")
        nodos_corredor = list(alcanzables.keys())

        hexes_corredor = {
            h3.latlng_to_cell(G_importante.nodes[n]["y"], G_importante.nodes[n]["x"], RESOLUCION_H3)
            for n in nodos_corredor
        }

        subgrafo_corredor = G_importante.subgraph(nodos_corredor)
        highways_corredor = [d.get("highway") for _, _, d in subgrafo_corredor.edges(data=True)]
        n_motorway = sum(1 for h in highways_corredor if es_via_importante(h) and
                          any(v in {"motorway", "motorway_link", "trunk", "trunk_link"} for v in (h if isinstance(h, list) else [h])))
        n_primaria_secundaria = len(highways_corredor) - n_motorway

        # accidentalidad del HEXÁGONO -- se conserva para poder comparar contra
        # la versión anterior, pero ya no alimenta el score: contaba todos los
        # siniestros del hexágono, incluidos los de calles sin relación con el
        # acceso, y en zonas céntricas densas eso inflaba el número
        accidentalidad = sum(siniestros_por_hex.get(h, 0) for h in hexes_corredor)

        # accidentalidad de la TRAZA: solo los siniestros que caen sobre el
        # corredor mismo (± BUFFER_TRAZA_M), normalizados por km de corredor.
        # Es una densidad lineal, que es la unidad natural del problema: un
        # control se pone sobre una vía, no sobre un área.
        traza, largo_km = traza_del_corredor(subgrafo_corredor)
        if traza is not None:
            en_traza = int(len(arbol_siniestros.query(traza.buffer(BUFFER_TRAZA_M), predicate="intersects")))
        else:
            en_traza = 0
        por_km = en_traza / largo_km if largo_km else 0.0

        riesgo_delictivo = sum(riesgo_por_hex.get(h, 0) for h in hexes_corredor) / len(hexes_corredor) if hexes_corredor else 0

        filas.append({
            "nombre": acceso["nombre"], "autopista": acceso["autopista"],
            "lat": acceso["lat"], "lon": acceso["lon"],
            "n_accesos_agrupados": len(grupo),
            # se guardan para poder dibujar el corredor en mapa (material de
            # presentación): sin esto el alcance de cada acceso no es visible
            "hexes_corredor": sorted(hexes_corredor),
            "accidentalidad_corredor": accidentalidad,
            "accidentalidad_por_hex": accidentalidad / len(hexes_corredor) if hexes_corredor else 0,
            # las dos que ahora importan: siniestros SOBRE la traza y su
            # densidad lineal, que es la que entra al score
            "siniestros_en_traza": en_traza,
            "largo_corredor_km": round(largo_km, 2),
            "siniestros_por_km": round(por_km, 2),
            "riesgo_delictivo_corredor": riesgo_delictivo,
            "tramos_troncales": n_motorway, "tramos_distribuidores": n_primaria_secundaria,
            "hexagonos_en_corredor": len(hexes_corredor), "nodos_alcanzados": len(nodos_corredor),
        })

    resultado = pd.DataFrame(filas)
    resultado["pct_accidentalidad"] = resultado["siniestros_por_km"].rank(pct=True)
    resultado["pct_riesgo"] = resultado["riesgo_delictivo_corredor"].rank(pct=True)
    resultado["score_control"] = (resultado["pct_accidentalidad"] + resultado["pct_riesgo"]) / 2
    resultado = resultado.sort_values("score_control", ascending=False).reset_index(drop=True)
    resultado["ranking"] = resultado.index + 1

    print(f"\nCorredor: nodos alcanzables por vías {sorted(JERARQUIAS_OSM_IMPORTANTES)} dentro de {RADIO_CORREDOR_M}m reales de cada acceso\n")
    print(resultado[[
        "ranking", "nombre", "autopista", "siniestros_en_traza", "largo_corredor_km",
        "siniestros_por_km", "accidentalidad_corredor", "riesgo_delictivo_corredor", "score_control",
    ]].to_string(index=False))

    FEATURES.mkdir(parents=True, exist_ok=True)
    resultado.to_parquet(FEATURES / "modulo_c_controles.parquet", index=False)
    print(f"\nGuardado: modulo_c_controles.parquet")


if __name__ == "__main__":
    main()
