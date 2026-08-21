"""
Qué tan pareja queda la cobertura del Módulo A entre las 15 comunas.

El MCLP tiene una restricción de equidad, pero es un **piso muy bajo**: exige
que quede al menos *un* hexágono cubierto por comuna. Con 401 hexágonos y
comunas de 20 a 40 cada una, cumplirla no dice casi nada sobre el reparto —
un plan puede satisfacerla y aun así dejar una comuna con el 3% de su riesgo
cubierto mientras otra llega al 90%. Nunca se midió qué pasa por encima de
ese piso, y es lo único que este script hace.

**La pregunta concreta**: el plan optimizado cubre más riesgo y más gente que
las 75 comisarías de hoy, pero ¿lo reparte mejor o peor? Optimizar un total
no dice nada sobre su distribución, y un optimizador que maximiza cobertura
agregada tiene todos los incentivos para concentrarla donde es barata.

Se mide sobre la misma matriz de cobertura y los mismos planes que
`cobertura_poblacion.py`, así que los números son comparables fila por fila.

Tres indicadores por escenario, y ninguno es un índice compuesto a propósito
—se pueden leer los tres por separado y ninguno esconde a los otros:

- **peor / mejor comuna**: los dos extremos, en cobertura de población.
- **brecha**: la diferencia en puntos entre esos dos extremos.
- **comunas por debajo del 10%**: cuántas quedan prácticamente sin cubrir,
  que es lo que la restricción de equidad permite sin violarse.

Salida: `data/features/equidad_cobertura.json`.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import osmnx as ox
import pandas as pd

from cobertura_poblacion import KS, con_poblacion
from modulo_a_patrullas import (
    GRAFO_PATH, RADIO_COBERTURA_M, TURNO,
    cargar_candidatos, cargar_demanda, matriz_cobertura_red, resolver_mclp,
)

RAIZ = Path(__file__).resolve().parent.parent.parent
FEATURES = RAIZ / "data" / "features"
SALIDA = FEATURES / "equidad_cobertura.json"

# Por debajo de esto una comuna está, a efectos prácticos, sin cubrir. Es un
# umbral elegido para leer la tabla, no un estándar: se reporta junto al
# detalle por comuna, así que quien no esté de acuerdo puede contar solo.
UMBRAL_SIN_CUBRIR = 0.10


def por_comuna(demanda: pd.DataFrame, cobertura: np.ndarray,
               activos: list[int]) -> pd.DataFrame:
    """Cobertura de riesgo y de población dentro de cada comuna.

    El denominador es el de la propia comuna, no el de la Ciudad: la pregunta
    es qué proporción de *lo suyo* queda cubierto. Con el denominador global,
    una comuna chica nunca podría verse bien cubierta y la tabla mediría
    tamaño en vez de reparto.
    """
    cubierto = (cobertura[:, activos].any(axis=1) if activos
                else np.zeros(len(demanda), dtype=bool))
    d = demanda.assign(cubierto=cubierto)
    filas = []
    for comuna, g in d.groupby("comuna_id"):
        filas.append({
            "comuna": int(comuna),
            "riesgo": float(g.loc[g["cubierto"], "score_riesgo"].sum() / g["score_riesgo"].sum()),
            "poblacion": float(g.loc[g["cubierto"], "poblacion_hex"].sum() / g["poblacion_hex"].sum()),
            "habitantes": round(float(g.loc[g["cubierto"], "poblacion_hex"].sum())),
            "n_hex": int(len(g)),
            "n_hex_cubiertos": int(g["cubierto"].sum()),
        })
    return pd.DataFrame(filas).sort_values("poblacion", ascending=False).reset_index(drop=True)


def resumen(tabla: pd.DataFrame) -> dict:
    p = tabla["poblacion"]
    return {
        "peor_comuna": int(tabla.loc[p.idxmin(), "comuna"]),
        "peor": float(p.min()),
        "mejor_comuna": int(tabla.loc[p.idxmax(), "comuna"]),
        "mejor": float(p.max()),
        "brecha": float(p.max() - p.min()),
        "mediana": float(p.median()),
        "sin_cubrir": int((p < UMBRAL_SIN_CUBRIR).sum()),
    }


def main() -> None:
    demanda = con_poblacion(cargar_demanda())
    candidatos = cargar_candidatos(demanda)
    print(f"Demanda: {len(demanda)} hexágonos · {demanda['comuna_id'].nunique()} comunas")

    print("Cargando grafo vial y calculando la matriz de cobertura (una sola vez)...")
    G = ox.io.load_graphml(GRAFO_PATH)
    cobertura = matriz_cobertura_red(demanda, candidatos, G)

    idx_actual = candidatos.index[candidatos["tipo"] == "comisaría existente"].tolist()
    hoy = por_comuna(demanda, cobertura, idx_actual)
    r_hoy = resumen(hoy)
    print(f"\nHOY ({len(idx_actual)} comisarías): peor comuna {r_hoy['peor']:.1%} "
          f"(C{r_hoy['peor_comuna']}), mejor {r_hoy['mejor']:.1%} (C{r_hoy['mejor_comuna']}), "
          f"brecha {r_hoy['brecha']:.1%}, {r_hoy['sin_cubrir']} comunas bajo el 10%\n")

    resultado = {
        "turno": TURNO,
        "radio_m": RADIO_COBERTURA_M,
        "umbral_sin_cubrir": UMBRAL_SIN_CUBRIR,
        "hoy": {"resumen": r_hoy, "comunas": hoy.to_dict(orient="records")},
        "curva": [],
        "planes": {},
    }

    for k in KS:
        elegidos, estado = resolver_mclp(demanda, candidatos, cobertura, k, devolver_estado=True)
        if estado != "Optimal":
            resultado["curva"].append({"k": k, "estado": estado})
            continue

        tabla = por_comuna(demanda, cobertura, elegidos)
        r = resumen(tabla)
        resultado["curva"].append({"k": k, "estado": estado, **r})
        # el detalle por comuna para todos los K: el tablero tiene un slider y
        # el panel tiene que poder seguirlo. Son 11 × 15 filas, 40 KB en total
        resultado["planes"][str(k)] = tabla.to_dict(orient="records")

        print(f"K={k:3d} -> peor {r['peor']:.1%} (C{r['peor_comuna']}), "
              f"mejor {r['mejor']:.1%} (C{r['mejor_comuna']}), brecha {r['brecha']:.1%}, "
              f"{r['sin_cubrir']} comunas bajo el 10%")

    SALIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nGuardado: {SALIDA}")


if __name__ == "__main__":
    main()
