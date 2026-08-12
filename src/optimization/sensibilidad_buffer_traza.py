"""
¿Qué tan frágil es el ranking del Módulo C al ancho del buffer sobre la traza?

Contar los siniestros "del corredor" exige decidir a qué distancia de la
calzada deja de contar uno. El módulo usa 30 m — margen que cubre el ancho de
vía más el error de geocodificación (los siniestros vienen geocodificados a
la dirección, no al punto del impacto). Es una elección, y si el orden se da
vuelta entre 20 y 50 m, el ranking es más frágil de lo que aparenta.

Se calculan las trazas UNA vez (lo caro: Dijkstra sobre el subgrafo de vías
importantes desde cada acceso) y se recuenta para cada buffer.

Uso: python sensibilidad_buffer_traza.py
"""

from __future__ import annotations

import json
from pathlib import Path

import h3
import networkx as nx
import osmnx as ox
import pandas as pd
from scipy.stats import spearmanr

from modulo_c_controles import (
    FEATURES, GRAFO_PATH, RADIO_CORREDOR_M, RESOLUCION_H3,
    cargar_siniestros_puntos, es_via_importante, traza_del_corredor,
)

BUFFERS_M = [10, 20, 30, 40, 50, 75]
REFERENCIA = 30
SALIDA = FEATURES / "sensibilidad_buffer_traza.json"


def main() -> None:
    accesos = pd.read_parquet(FEATURES / "accesos_autopistas_hex.parquet").dropna(subset=["lat", "lon"])
    G = ox.io.load_graphml(GRAFO_PATH)
    edges = [(u, v, k) for u, v, k, d in G.edges(keys=True, data=True) if es_via_importante(d.get("highway"))]
    G_imp = G.edge_subgraph(edges).copy()
    accesos = accesos.reset_index(drop=True)
    accesos["nodo_grafo"] = ox.distance.nearest_nodes(G_imp, accesos["lon"].to_numpy(), accesos["lat"].to_numpy())

    arbol, _ = cargar_siniestros_puntos()
    riesgo = pd.read_parquet(FEATURES / "riesgo_predicho.parquet")
    riesgo_por_hex = riesgo.groupby("hex_id", observed=True)["score_riesgo"].mean()

    corredores = []
    for nodo, grupo in accesos.groupby("nodo_grafo", sort=False):
        alcanzables = nx.single_source_dijkstra_path_length(G_imp, nodo, cutoff=RADIO_CORREDOR_M, weight="length")
        nodos = list(alcanzables.keys())
        hexes = {h3.latlng_to_cell(G_imp.nodes[n]["y"], G_imp.nodes[n]["x"], RESOLUCION_H3) for n in nodos}
        traza, largo = traza_del_corredor(G_imp.subgraph(nodos))
        corredores.append({
            "nombre": " / ".join(sorted(grupo["nombre"])).split(" / ")[0],
            "traza": traza, "largo_km": largo,
            "riesgo": sum(riesgo_por_hex.get(h, 0) for h in hexes) / len(hexes) if hexes else 0,
        })
    print(f"{len(corredores)} corredores únicos\n")

    rankings: dict[int, pd.DataFrame] = {}
    for b in BUFFERS_M:
        filas = []
        for c in corredores:
            n = int(len(arbol.query(c["traza"].buffer(b), predicate="intersects"))) if c["traza"] is not None else 0
            filas.append({"nombre": c["nombre"], "en_traza": n,
                          "por_km": n / c["largo_km"] if c["largo_km"] else 0.0, "riesgo": c["riesgo"]})
        df = pd.DataFrame(filas)
        df["score"] = (df["por_km"].rank(pct=True) + df["riesgo"].rank(pct=True)) / 2
        df = df.sort_values("score", ascending=False).reset_index(drop=True)
        df["puesto"] = df.index + 1
        rankings[b] = df
        top2 = " / ".join(df["nombre"].head(2))
        print(f"buffer {b:3d}m -> {int(df['en_traza'].sum()):6,} siniestros en traza | top2: {top2}")

    ref = rankings[REFERENCIA].set_index("nombre")["puesto"]
    print(f"\nEstabilidad contra el buffer de referencia ({REFERENCIA}m):")
    resumen = []
    for b in BUFFERS_M:
        otro = rankings[b].set_index("nombre")["puesto"].reindex(ref.index)
        rho = spearmanr(ref.to_numpy(), otro.to_numpy()).statistic
        movidos = int((ref != otro).sum())
        max_salto = int((ref - otro).abs().max())
        # ojo: comparar los dos primeros como CONJUNTO oculta que se den vuelta
        # entre sí, que es justo lo que pasa a partir de 40m. Se compara el orden.
        top2_ref = list(rankings[REFERENCIA]["nombre"].head(2))
        top2_b = list(rankings[b]["nombre"].head(2))
        resumen.append({"buffer_m": b, "spearman": round(float(rho), 3), "puestos_que_cambian": movidos,
                        "salto_maximo": max_salto, "mismo_par_top2": set(top2_b) == set(top2_ref),
                        "mismo_orden_top2": top2_b == top2_ref, "primero": top2_b[0]})
        print(f"  {b:3d}m: rho={rho:.3f} | cambian {movidos}/{len(ref)} puestos | salto máx {max_salto} | "
              f"1º: {top2_b[0][:22]:22s} {'(=)' if top2_b == top2_ref else '(SE DA VUELTA)'}")

    SALIDA.write_text(json.dumps({
        "referencia_m": REFERENCIA, "buffers": resumen,
        "rankings": {str(b): rankings[b][["puesto", "nombre", "en_traza", "por_km"]].round(2).to_dict("records")
                     for b in BUFFERS_M},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nGuardado: {SALIDA.name}")


if __name__ == "__main__":
    main()
