"""
Cobertura de **población**, no solo de riesgo, para el Módulo A.

El tablero dice "las 75 comisarías cubren 35,1%" y ese porcentaje es de
riesgo predicho. Es la métrica correcta para priorizar, pero no se puede
dimensionar: nadie sabe cuánto es "35,1% del riesgo". La pregunta que sí se
dimensiona sola es **cuánta gente vive a menos de 800 m de calle real de una
comisaría**, y estaba a un cálculo de distancia: la demanda del MCLP son los
mismos 401 hexágonos para los que `hex_poblacion.parquet` tiene población
prorrateada.

Este script mide tres cosas sobre la misma matriz de cobertura:

1. **Cuánta población cubre el plan que optimiza riesgo** — el que el tablero
   ya muestra. Es la traducción del número interno a habitantes.
2. **Cuánta cubriría un plan que optimizara población.** Es el techo de esa
   métrica, y sirve para saber cuánto se está "dejando sobre la mesa".
3. **Cuánto se parecen los dos planes.** Si coincidieran, la distinción sería
   académica; si no, hay una decisión de política adentro del optimizador que
   hasta ahora no estaba a la vista.

**El punto de la comparación no es que uno sea mejor.** Riesgo y población no
están igual de repartidos —el microcentro concentra delito con poca gente
viviendo ahí, y el sur tiene mucha gente y menos delito registrado— así que
los dos objetivos tiran para lados distintos por construcción. Lo que este
script deja medido es cuánto, para que la elección sea explícita.

Corre sobre la misma formulación que `modulo_a_patrullas.py` (misma
restricción de equidad por comuna, mismo radio, mismos candidatos): lo único
que cambia entre las dos corridas es la columna que se maximiza. Si mañana
cambia el MCLP, las dos ramas heredan el cambio.

Salida: `data/features/cobertura_poblacion.json`.
"""

from __future__ import annotations

import json
from pathlib import Path

import osmnx as ox
import pandas as pd

from modulo_a_patrullas import (
    GRAFO_PATH, RADIO_COBERTURA_M, TURNO,
    cargar_candidatos, cargar_demanda, cobertura_lograda,
    matriz_cobertura_red, resolver_mclp,
)

RAIZ = Path(__file__).resolve().parent.parent.parent
FEATURES = RAIZ / "data" / "features"
SALIDA = FEATURES / "cobertura_poblacion.json"

# Los mismos K que la curva de riesgo, para que las dos series se puedan
# poner en el mismo gráfico sin interpolar nada.
KS = [5, 10, 15, 20, 30, 40, 50, 60, 75, 90, 110]


def con_poblacion(demanda: pd.DataFrame) -> pd.DataFrame:
    """Suma la población de cada hexágono a la tabla de demanda.

    `hex_poblacion.parquet` tiene los 401 hexágonos con habitantes prorrateados
    por área dentro de su barrio (ver `overlay_poligonos.py`). Un hexágono sin
    fila ahí no es un hexágono vacío sino uno que no se pudo cruzar, y contarlo
    como cero sesgaría la cobertura hacia arriba —queda fuera del denominador
    igual que del numerador—, así que se corta si aparece alguno.
    """
    pob = pd.read_parquet(FEATURES / "hex_poblacion.parquet")
    pob["hex_id"] = pob["hex_id"].astype(str)
    d = demanda.copy()
    d["hex_id"] = d["hex_id"].astype(str)
    d = d.merge(pob, on="hex_id", how="left")
    faltan = int(d["poblacion_hex"].isna().sum())
    if faltan:
        raise SystemExit(f"{faltan} hexágonos de demanda sin población: no se puede "
                         f"medir cobertura poblacional sin decidir qué son.")
    return d


def solape(a: list[int], b: list[int]) -> float:
    """Fracción de las ubicaciones de `a` que también están en `b`."""
    if not a:
        return 0.0
    return len(set(a) & set(b)) / len(a)


def main() -> None:
    demanda = con_poblacion(cargar_demanda())
    candidatos = cargar_candidatos(demanda)
    total_hab = float(demanda["poblacion_hex"].sum())
    print(f"Demanda: {len(demanda)} hexágonos (turno {TURNO}) · {total_hab:,.0f} habitantes")

    print("Cargando grafo vial y calculando la matriz de cobertura (una sola vez)...")
    G = ox.io.load_graphml(GRAFO_PATH)
    cobertura = matriz_cobertura_red(demanda, candidatos, G)

    idx_actual = candidatos.index[candidatos["tipo"] == "comisaría existente"].tolist()
    riesgo_actual = cobertura_lograda(demanda, cobertura, idx_actual)
    pob_actual = cobertura_lograda(demanda, cobertura, idx_actual, peso="poblacion_hex")
    print(f"\nHOY ({len(idx_actual)} comisarías): {riesgo_actual:.1%} del riesgo · "
          f"{pob_actual:.1%} de la población ({pob_actual * total_hab:,.0f} personas)\n")

    resultado = {
        "turno": TURNO,
        "radio_m": RADIO_COBERTURA_M,
        "n_demanda": int(len(demanda)),
        "n_comisarias": len(idx_actual),
        "poblacion_total": round(total_hab),
        "actual": {
            "riesgo": float(riesgo_actual),
            "poblacion": float(pob_actual),
            "habitantes": round(pob_actual * total_hab),
        },
        "curva": [],
    }

    for k in KS:
        fila: dict = {"k": k}

        elegidos_r, estado_r = resolver_mclp(
            demanda, candidatos, cobertura, k, devolver_estado=True)
        elegidos_p, estado_p = resolver_mclp(
            demanda, candidatos, cobertura, k, devolver_estado=True, peso="poblacion_hex")

        # los dos objetivos comparten la restricción de equidad, así que o los
        # dos son factibles o ninguno; se chequean igual por separado para no
        # asumirlo
        if estado_r != "Optimal" or estado_p != "Optimal":
            print(f"K={k:3d} -> infactible (riesgo: {estado_r}, población: {estado_p})")
            resultado["curva"].append({**fila, "estado": estado_r, "riesgo": None,
                                       "poblacion": None})
            continue

        fila["estado"] = "Optimal"
        fila["riesgo"] = float(cobertura_lograda(demanda, cobertura, elegidos_r))
        fila["poblacion"] = float(
            cobertura_lograda(demanda, cobertura, elegidos_r, peso="poblacion_hex"))
        # el mismo K, pero maximizando gente: cuánto más población se podría
        # cubrir y cuánto riesgo cuesta hacerlo
        fila["poblacion_si_optimiza_poblacion"] = float(
            cobertura_lograda(demanda, cobertura, elegidos_p, peso="poblacion_hex"))
        fila["riesgo_si_optimiza_poblacion"] = float(
            cobertura_lograda(demanda, cobertura, elegidos_p))
        fila["solape_planes"] = float(solape(elegidos_r, elegidos_p))
        fila["habitantes"] = round(fila["poblacion"] * total_hab)

        print(f"K={k:3d} -> riesgo {fila['riesgo']:.1%} · población {fila['poblacion']:.1%} "
              f"({fila['habitantes']:,} personas) | optimizando población: "
              f"{fila['poblacion_si_optimiza_poblacion']:.1%} de gente pero "
              f"{fila['riesgo_si_optimiza_poblacion']:.1%} de riesgo · "
              f"solape {fila['solape_planes']:.0%}")
        resultado["curva"].append(fila)

    SALIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nGuardado: {SALIDA}")


if __name__ == "__main__":
    main()
