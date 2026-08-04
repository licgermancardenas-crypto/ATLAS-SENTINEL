"""
CAPA 3 — auditoría de equidad (P0, ver auditoría técnica externa): el
modelo aprende de delitos DENUNCIADOS, no de delito real. Si el
patrullaje histórico ya estuvo sesgado hacia ciertas zonas, el riesgo
"aprendido" puede estar formalizando ese sesgo en vez de midiendo riesgo
genuino (Lum & Isaac 2016, Ensign et al. 2018 — feedback loops en
predictive policing).

Este script no puede resolver el problema de fondo (no hay forma de
medir "delito real" independiente del registro policial con los datos
disponibles). Lo que sí puede hacer es la pregunta operacionalizable:
¿el riesgo predicho correlaciona con vulnerabilidad socioeconómica (NBI,
hacinamiento) MÁS de lo que el historial delictivo por sí solo explica?
Si sí, es señal de que el modelo está usando NBI/hacinamiento (u otra
variable correlacionada con pobreza estructural) como proxy de clase
social en vez de riesgo — un patrón a vigilar, no una prueba definitiva.

Método: correlación simple de score_riesgo vs. NBI/hacinamiento por
comuna, y correlación PARCIAL controlando por el nivel histórico de
delitos de la comuna (si la correlación con NBI cae a ~0 al controlar
por historial, el modelo está usando NBI como proxy de historial, no de
clase social per se — lectura más benigna; si se mantiene alta, es la
señal de alerta).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROCESSED = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"


def correlacion_parcial(x: pd.Series, y: pd.Series, control: pd.Series) -> float:
    """Correlación de Pearson entre x e y, controlando por `control`
    (regresión de x e y contra control, correlación de los residuos)."""
    def residuos(v: pd.Series) -> np.ndarray:
        c = np.vstack([control, np.ones(len(control))]).T
        beta, *_ = np.linalg.lstsq(c, v, rcond=None)
        return v - c @ beta

    return np.corrcoef(residuos(x), residuos(y))[0, 1]


def main() -> None:
    riesgo = pd.read_parquet(FEATURES / "riesgo_predicho.parquet")
    riesgo_comuna = riesgo.groupby("comuna_id")["score_riesgo"].mean().rename("riesgo_medio")

    socio = pd.read_parquet(PROCESSED / "socioeconomico_comuna.parquet").rename(columns={"comuna": "comuna_id"})
    socio = socio.set_index("comuna_id")

    delitos = pd.read_parquet(FEATURES / "delitos_hex.parquet", columns=["hex_id", "anio"])
    hex_maestra = pd.read_parquet(FEATURES / "hex_maestra.parquet")[["hex_id", "comuna_id"]].dropna()
    delitos = delitos.merge(hex_maestra, on="hex_id", how="left")
    historico_comuna = delitos[delitos["anio"] <= 2023].groupby("comuna_id").size().rename("delitos_historicos_train")

    tabla = pd.concat([riesgo_comuna, socio, historico_comuna], axis=1).dropna()
    print(f"Comunas con datos completos: {len(tabla)}\n")
    print(tabla.round(2))

    print("\n=== Correlación simple (score_riesgo vs. variable socioeconómica) ===")
    for col in ["pct_hogares_nbi", "pct_hacinamiento_critico"]:
        r_simple = tabla["riesgo_medio"].corr(tabla[col])
        print(f"  {col}: r={r_simple:.3f}")

    print("\n=== Correlación PARCIAL, controlando por historial delictivo de la comuna ===")
    for col in ["pct_hogares_nbi", "pct_hacinamiento_critico"]:
        r_parcial = correlacion_parcial(
            tabla["riesgo_medio"].to_numpy(), tabla[col].to_numpy(), tabla["delitos_historicos_train"].to_numpy()
        )
        print(f"  {col}: r_parcial={r_parcial:.3f}")

    print("\nLectura: si r_parcial cae cerca de 0 respecto a r simple, el riesgo predicho covaría con NBI/hacinamiento")
    print("principalmente PORQUE esas comunas ya tenían más historial delictivo (relación indirecta, más benigna).")
    print("Si r_parcial se mantiene alto, el modelo está capturando algo de NBI/hacinamiento más allá del historial")
    print("— podría ser señal genuina de riesgo estructural, o el proxy de clase social que este audit busca vigilar.")
    print("Esto NO es una prueba de sesgo policial (no hay dato de 'delito real' para contrastar) — es un chequeo")
    print("de qué tan independiente es el riesgo predicho de la vulnerabilidad socioeconómica, documentado para que")
    print("quien use el sistema sepa qué está y qué no está midiendo.")


if __name__ == "__main__":
    main()
