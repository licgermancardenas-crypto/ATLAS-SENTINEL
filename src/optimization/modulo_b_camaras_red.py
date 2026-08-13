"""
CAPA 2, Módulo B — versión sobre la RED VIAL.

POR QUÉ SE REHIZO
La versión sobre hexágonos no resolvía un problema de cobertura: los
centroides H3-8 están a 700m unos de otros y el radio de cámara es 150m, así
que cada candidato cubría únicamente su propio hexágono. La matriz de
cobertura era la identidad y el "Weighted Max Coverage" degeneraba en
"elegir los N hexágonos de mayor peso" (ver README). El número que reportaba
tampoco era cobertura sino concentración.

QUÉ CAMBIA
El problema estaba mal planteado por mezclar dos resoluciones: el riesgo se
modela a H3-8 y la decisión se toma a escala de esquina. En vez de forzar el
riesgo a una grilla más fina —que sería inventar detalle que el modelo no
tiene— se mantiene el riesgo donde está y se cambia el UNIVERSO:

- Demanda: los 37.036 tramos de calle del grafo de OSM, cada uno pesado por
  su largo × el peso del hexágono que lo contiene. La mediana de tramo es
  103m contra un radio de 150m: a esta escala los 150m SÍ discriminan entre
  tramos vecinos, que es lo que la versión anterior no lograba.
- Candidatos: las intersecciones del grafo, que es donde físicamente se monta
  una cámara (poste de esquina), no un centroide abstracto.
- Cobertura: un tramo está cubierto si alguno de sus extremos queda a <=150m
  de distancia de CALLE de la cámara — no en línea recta.

Se conserva del módulo original la ponderación, que es la parte defendible:
riesgo × boost por baja iluminación × boost por flujo peatonal, con descuento
si ya hay una cámara cerca. Y el greedy, porque el documento pide un ranking
por ganancia marginal.

Uso: python modulo_b_camaras_red.py [n_camaras]
"""

from __future__ import annotations

import sys
from pathlib import Path

import h3
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd

from modulo_b_camaras import (
    DESCUENTO_YA_CUBIERTO, RADIO_COBERTURA_M, RADIO_EXCLUSION_M,
    cargar_demanda, coords_metros,
)

PROCESSED = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
GRAFO_PATH = FEATURES / "grafo_vial.graphml"

N_CAMARAS = 30
RESOLUCION_H3 = 8


def hex_de(lat: float, lon: float) -> str:
    return h3.latlng_to_cell(lat, lon, RESOLUCION_H3)


def main() -> None:
    n_camaras = int(sys.argv[1]) if len(sys.argv) > 1 else N_CAMARAS

    demanda_hex = cargar_demanda().set_index("hex_id")
    print(f"Peso por hexágono cargado: {len(demanda_hex)} hexágonos")

    G = ox.io.load_graphml(GRAFO_PATH)
    nodos = list(G.nodes)
    idx_nodo = {n: i for i, n in enumerate(nodos)}
    print(f"Grafo: {len(nodos):,} intersecciones, {G.number_of_edges():,} tramos")

    # --- demanda: un tramo por arista, pesado por largo x peso del hexágono ---
    aristas, peso_tramo, extremos = [], [], []
    for u, v, k, d in G.edges(keys=True, data=True):
        largo = float(d.get("length", 0.0))
        lat = (G.nodes[u]["y"] + G.nodes[v]["y"]) / 2
        lon = (G.nodes[u]["x"] + G.nodes[v]["x"]) / 2
        p = demanda_hex["peso"].get(hex_de(lat, lon), 0.0)
        aristas.append((u, v, k))
        peso_tramo.append(largo / 1000 * p)  # km x peso
        extremos.append((idx_nodo[u], idx_nodo[v]))
    peso_tramo = np.array(peso_tramo, dtype="float64")
    extremos = np.array(extremos, dtype="int32")
    print(f"Demanda: {len(peso_tramo):,} tramos | peso bruto {peso_tramo.sum():.1f} (antes del descuento)")

    # --- cámaras existentes: descuento a lo ya cubierto, exclusión de candidatos ---
    camaras = pd.read_parquet(PROCESSED / "camaras.parquet").dropna(subset=["latitud", "longitud"])
    camaras = camaras.rename(columns={"latitud": "lat", "longitud": "lon"})
    cam_xy = coords_metros(camaras)
    nodo_xy = coords_metros(pd.DataFrame({"lat": [G.nodes[n]["y"] for n in nodos],
                                          "lon": [G.nodes[n]["x"] for n in nodos]}))
    d_nodo_cam = np.sqrt(((nodo_xy[:, None, :] - cam_xy[None, :, :]) ** 2).sum(axis=2))
    dist_min = d_nodo_cam.min(axis=1)
    del d_nodo_cam

    ya_cubierto = (dist_min[extremos[:, 0]] <= RADIO_COBERTURA_M) | (dist_min[extremos[:, 1]] <= RADIO_COBERTURA_M)
    peso_tramo[ya_cubierto] *= DESCUENTO_YA_CUBIERTO
    excluidos = dist_min <= RADIO_EXCLUSION_M
    print(f"Tramos con cámara existente a <={RADIO_COBERTURA_M}m: {int(ya_cubierto.sum()):,} "
          f"({ya_cubierto.mean():.1%}) — pesan {DESCUENTO_YA_CUBIERTO:.0%}")
    print(f"Intersecciones excluidas como candidatas (<{RADIO_EXCLUSION_M}m de una cámara): {int(excluidos.sum()):,}")
    print(f"Peso total tras el descuento (denominador de la cobertura): {peso_tramo.sum():.1f}")

    # --- cobertura por distancia de calle desde cada intersección candidata ---
    print(f"Calculando cobertura a {RADIO_COBERTURA_M}m de calle desde cada intersección...")
    Gu = G.to_undirected()  # una cámara ve la calle en ambos sentidos
    aristas_de_nodo: dict[int, list[int]] = {}
    for e, (a, b) in enumerate(extremos):
        aristas_de_nodo.setdefault(a, []).append(e)
        aristas_de_nodo.setdefault(b, []).append(e)

    cubre: list[np.ndarray] = []
    for i, n in enumerate(nodos):
        if excluidos[i]:
            cubre.append(np.empty(0, dtype="int32"))
            continue
        alcanzables = nx.single_source_dijkstra_path_length(Gu, n, cutoff=RADIO_COBERTURA_M, weight="length")
        vistos: set[int] = set()
        for m in alcanzables:
            vistos.update(aristas_de_nodo.get(idx_nodo[m], ()))
        cubre.append(np.fromiter(vistos, dtype="int32", count=len(vistos)))
    tam = np.array([len(c) for c in cubre])
    print(f"  tramos cubiertos por candidato: mediana {np.median(tam[tam > 0]):.0f} | máx {tam.max()}")

    # --- greedy por ganancia marginal ---
    cubierto = np.zeros(len(peso_tramo), dtype=bool)
    elegidas = []
    for paso in range(n_camaras):
        mejor, mejor_g = -1, 0.0
        for i, ids in enumerate(cubre):
            if ids.size == 0:
                continue
            g = peso_tramo[ids][~cubierto[ids]].sum()
            if g > mejor_g:
                mejor, mejor_g = i, g
        if mejor < 0:
            break
        cubierto[cubre[mejor]] = True
        n = nodos[mejor]
        elegidas.append({
            "ranking": paso + 1, "nodo": n,
            "lat": G.nodes[n]["y"], "lon": G.nodes[n]["x"],
            "hex_id": hex_de(G.nodes[n]["y"], G.nodes[n]["x"]),
            "ganancia_marginal": round(float(mejor_g), 4),
            "tramos_cubiertos": int(cubre[mejor].size),
        })
        cubre[mejor] = np.empty(0, dtype="int32")

    res = pd.DataFrame(elegidas)
    pct = peso_tramo[cubierto].sum() / peso_tramo.sum()
    km = sum(float(G.edges[aristas[e]].get("length", 0)) for e in np.where(cubierto)[0]) / 1000

    print(f"\n{len(res)} cámaras sobre la red vial cubren {pct:.1%} del riesgo ponderado "
          f"({km:.1f} km de calle)")
    print(res[["ranking", "hex_id", "tramos_cubiertos", "ganancia_marginal"]].head(10).to_string(index=False))

    # el peso total va en el parquet: sin el no se puede reconstruir la curva
    # de cobertura acumulada desde las ganancias marginales
    res["peso_total"] = peso_tramo.sum()
    ruta = FEATURES / "modulo_b_camaras_red.parquet"
    res.to_parquet(ruta, index=False)
    print(f"\nGuardado: {ruta.name}")


if __name__ == "__main__":
    main()
