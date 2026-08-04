"""
P1 de la auditoría técnica externa (sección 7): Módulo A medía cobertura
en distancia euclidiana sobre CRS métrico, no en distancia real de red
vial — 800m en línea recta puede ser 1.400m reales si hay que rodear una
autopista o ir contra el sentido de una calle de un carril. Módulo C
aproximaba el "corredor" de cada acceso con un buffer de radio fijo en
vez de recorrer la topología real.

Ambas debilidades se resuelven con una sola pieza de infraestructura: el
grafo vial real. Se usa OpenStreetMap vía osmnx en vez de reconstruir
topología a mano desde calles.parquet (que son geometrías sueltas sin
nodos compartidos armados, y snapear manualmente floats de lat/lon para
inferir qué tramos se tocan es frágil) — OSM ya trae el grafo noded,
direcciones de circulación, y jerarquía vial (`highway`) equivalente a
la clasificación de GCBA.

Se descarga una sola vez y se cachea en disco (GraphML) — bajar el grafo
completo de CABA por Overpass API tarda unos minutos, no tiene sentido
repetirlo en cada corrida de Módulo A/C.
"""

from __future__ import annotations

from pathlib import Path

import osmnx as ox
import pandas as pd
from shapely import wkt
from shapely.ops import unary_union

PROCESSED = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
GRAFO_PATH = FEATURES / "grafo_vial.graphml"


def main() -> None:
    barrios = pd.read_parquet(PROCESSED / "barrios.parquet")
    boundary = unary_union(barrios["geometry_wkt"].map(wkt.loads).to_list())
    print(f"Polígono de CABA: {boundary.area:.5f} grados², descargando grafo vial de OSM (puede tardar unos minutos)...")

    G = ox.graph_from_polygon(boundary, network_type="drive", simplify=True)
    print(f"Grafo: {G.number_of_nodes():,} nodos, {G.number_of_edges():,} tramos (edges dirigidos)")

    G = ox.routing.add_edge_speeds(G)
    G = ox.routing.add_edge_travel_times(G)

    FEATURES.mkdir(parents=True, exist_ok=True)
    ox.io.save_graphml(G, GRAFO_PATH)
    print(f"Guardado: {GRAFO_PATH}")

    highway_counts = pd.Series([d.get("highway") for _, _, d in G.edges(data=True)]).astype(str).value_counts()
    print("\nDistribución por jerarquía OSM (highway):")
    print(highway_counts)


if __name__ == "__main__":
    main()
