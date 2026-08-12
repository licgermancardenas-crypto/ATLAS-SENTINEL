"""
¿Se asignan las patrullas en los mismos lugares para robo que para lesiones?

Resuelve el MCLP del Módulo A una vez por superficie de riesgo (cada tipo de
delito, más la combinada y la agregada de producción) y mide cuánto se
superponen los planes resultantes.

POR QUÉ IMPORTA
Desagregar por tipo mejoró la predicción del CONTEO (ver README). Pero los
módulos no optimizan conteos: optimizan una priorización espacial. Si las
superficies rankean casi igual —y su correlación de Spearman es 0,84-0,92—
los planes van a ser casi idénticos y desagregar no cambiaría ninguna
decisión operativa. Eso es una hipótesis, y este script la mide en vez de
suponerla.

Reusa las funciones de modulo_a_patrullas.py: la matriz de cobertura por
distancia de red es lo caro (~6s de Dijkstra desde 476 candidatos) y se
calcula UNA vez para todas las superficies.

Uso: python comparar_modulo_a_por_tipo.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import osmnx as ox
import pandas as pd

from modulo_a_patrullas import (
    GRAFO_PATH, K_PATRULLAS, RADIO_COBERTURA_M, TURNO,
    cargar_candidatos, matriz_cobertura_red, resolver_mclp,
)

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
SALIDA = FEATURES / "comparacion_modulo_a_por_tipo.json"


def cobertura_de(demanda: pd.DataFrame, cobertura: np.ndarray, activos: list[int], col: str) -> float:
    if not activos:
        return 0.0
    cubierto = cobertura[:, activos].any(axis=1)
    total = demanda[col].sum()
    return float(demanda.loc[cubierto, col].sum() / total) if total else 0.0


def main() -> None:
    por_tipo = pd.read_parquet(FEATURES / "riesgo_predicho_por_tipo.parquet")
    agregado = pd.read_parquet(FEATURES / "riesgo_predicho.parquet")

    demanda = por_tipo[por_tipo["turno"] == TURNO].copy().reset_index(drop=True)
    agg_turno = agregado[agregado["turno"] == TURNO][["hex_id", "score_riesgo"]]
    demanda = demanda.merge(agg_turno, on="hex_id", how="left")
    demanda["score_riesgo"] = demanda["score_riesgo"].fillna(0)

    superficies = [c for c in demanda.columns if c.startswith("score_")]
    print(f"turno {TURNO} | {len(demanda)} hexágonos | K={K_PATRULLAS} | superficies: {superficies}")

    candidatos = cargar_candidatos(demanda)
    print("calculando matriz de cobertura (una vez para todas)...")
    G = ox.io.load_graphml(GRAFO_PATH)
    cobertura = matriz_cobertura_red(demanda, candidatos, G)

    planes: dict[str, list[int]] = {}
    filas = []
    for col in superficies:
        # se descartan las OTRAS superficies antes de renombrar: si no, al
        # renombrar score_lesiones -> score_riesgo quedan dos columnas con el
        # mismo nombre (la agregada ya se llama así) y resolver_mclp termina
        # optimizando un DataFrame en vez de una Serie, en silencio
        otras = [c for c in superficies if c != col]
        d = demanda.drop(columns=otras).rename(columns={col: "score_riesgo"})
        assert d.columns.tolist().count("score_riesgo") == 1, "columna de score duplicada"
        elegidos, estado = resolver_mclp(d, candidatos, cobertura, K_PATRULLAS, devolver_estado=True)
        if estado != "Optimal":
            print(f"  {col}: {estado} — se descarta")
            continue
        planes[col] = elegidos
        filas.append({
            "superficie": col,
            "cobertura_propia": round(cobertura_de(demanda, cobertura, elegidos, col), 4),
            "n_ubicaciones": len(elegidos),
        })
        print(f"  {col:20s} -> cubre {filas[-1]['cobertura_propia']:.1%} de su propio riesgo")

    print("\nSuperposición de planes (ubicaciones en común sobre K):")
    nombres = list(planes)
    matriz = pd.DataFrame(index=nombres, columns=nombres, dtype=float)
    for a in nombres:
        for b in nombres:
            comun = len(set(planes[a]) & set(planes[b]))
            matriz.loc[a, b] = round(comun / K_PATRULLAS, 3)
    print(matriz.to_string())

    # cuánto se pierde por usar el plan de otra superficie en vez del propio
    print("\nCosto de usar el plan de otro tipo (cobertura del riesgo de la FILA"
          " usando el plan de la COLUMNA, relativo a su plan óptimo):")
    perdida = pd.DataFrame(index=nombres, columns=nombres, dtype=float)
    for a in nombres:
        propio = cobertura_de(demanda, cobertura, planes[a], a)
        for b in nombres:
            usando = cobertura_de(demanda, cobertura, planes[b], a)
            perdida.loc[a, b] = round(usando / propio, 3) if propio else float("nan")
    print(perdida.to_string())

    SALIDA.write_text(json.dumps({
        "turno": TURNO, "k": K_PATRULLAS, "radio_m": RADIO_COBERTURA_M,
        "cobertura": filas,
        "superposicion": matriz.to_dict(),
        "retencion_cruzada": perdida.to_dict(),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nGuardado: {SALIDA.name}")


if __name__ == "__main__":
    main()
