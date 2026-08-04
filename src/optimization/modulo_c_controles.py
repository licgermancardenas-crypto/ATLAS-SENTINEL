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
"""

from __future__ import annotations

from pathlib import Path

import h3
import networkx as nx
import osmnx as ox
import pandas as pd

PROCESSED = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
GRAFO_PATH = FEATURES / "grafo_vial.graphml"

RADIO_CORREDOR_M = 2000
JERARQUIAS_OSM_IMPORTANTES = {"motorway", "trunk", "primary", "secondary",
                               "motorway_link", "trunk_link", "primary_link", "secondary_link"}
RESOLUCION_H3 = 8


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

    siniestros = pd.read_parquet(FEATURES / "siniestros_hechos_hex.parquet")
    siniestros_por_hex = siniestros.groupby("hex_id", observed=True).size()

    riesgo = pd.read_parquet(FEATURES / "riesgo_predicho.parquet")
    riesgo_por_hex = riesgo.groupby("hex_id", observed=True)["score_riesgo"].mean()

    filas = []
    for (_, acceso), nodo in zip(accesos.reset_index(drop=True).iterrows(), nodo_acceso):
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

        accidentalidad = sum(siniestros_por_hex.get(h, 0) for h in hexes_corredor)
        riesgo_delictivo = sum(riesgo_por_hex.get(h, 0) for h in hexes_corredor) / len(hexes_corredor) if hexes_corredor else 0

        filas.append({
            "nombre": acceso["nombre"], "autopista": acceso["autopista"],
            "accidentalidad_corredor": accidentalidad, "riesgo_delictivo_corredor": riesgo_delictivo,
            "tramos_troncales": n_motorway, "tramos_distribuidores": n_primaria_secundaria,
            "hexagonos_en_corredor": len(hexes_corredor), "nodos_alcanzados": len(nodos_corredor),
        })

    resultado = pd.DataFrame(filas)
    resultado["pct_accidentalidad"] = resultado["accidentalidad_corredor"].rank(pct=True)
    resultado["pct_riesgo"] = resultado["riesgo_delictivo_corredor"].rank(pct=True)
    resultado["score_control"] = (resultado["pct_accidentalidad"] + resultado["pct_riesgo"]) / 2
    resultado = resultado.sort_values("score_control", ascending=False).reset_index(drop=True)
    resultado["ranking"] = resultado.index + 1

    print(f"\nCorredor: nodos alcanzables por vías {sorted(JERARQUIAS_OSM_IMPORTANTES)} dentro de {RADIO_CORREDOR_M}m reales de cada acceso\n")
    print(resultado[[
        "ranking", "nombre", "autopista", "accidentalidad_corredor",
        "riesgo_delictivo_corredor", "hexagonos_en_corredor", "score_control",
    ]].to_string(index=False))

    FEATURES.mkdir(parents=True, exist_ok=True)
    resultado.to_parquet(FEATURES / "modulo_c_controles.parquet", index=False)
    print(f"\nGuardado: modulo_c_controles.parquet")


if __name__ == "__main__":
    main()
