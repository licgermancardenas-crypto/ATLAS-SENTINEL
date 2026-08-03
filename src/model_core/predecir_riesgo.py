"""
CAPA 1, sección 3.5: genera la tabla riesgo_predicho que consumen los
módulos de Capa 2 — acá simplificada a grano (hex_id, turno), sin fecha,
porque los módulos de decisión necesitan un score estable de "cómo es el
riesgo típico de este hex en este turno hoy en día", no una predicción
puntual para un día calendario específico.

Se usa el modelo v1 (sin exógenas), no v2: v2 no mejoró el Recall@K (ver
README) y además depender de exógenas para "predecir hoy" requeriría
clima/eventos del futuro, que no existen — v1 solo necesita variables que
ya se conocen de antemano (histórico, socioeconómico, infraestructura).

El score es el promedio del conteo esperado por el modelo sobre 2025
(el período de test, el más reciente y no usado para entrenar) para cada
combinación hex×turno.
"""

from __future__ import annotations

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from train_baseline import CATEGORICAS, FEATURES_COLS

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
MODELS_DIR = FEATURES / "modelos"


def main() -> None:
    tabla = pd.read_parquet(FEATURES / "training_table.parquet")
    for col in CATEGORICAS:
        tabla[col] = tabla[col].astype("category")
    test = tabla[tabla["fecha"].dt.year == 2025].copy()

    modelo = lgb.Booster(model_file=str(MODELS_DIR / "modelo_nucleo_v1.txt"))
    test["conteo_esperado"] = np.clip(modelo.predict(test[FEATURES_COLS]), 0, None)

    riesgo = test.groupby(["hex_id", "turno"], observed=True).agg(
        score_riesgo=("conteo_esperado", "mean"),
        poblacion=("poblacion_total", "first"),
    ).reset_index()

    hex_maestra = pd.read_parquet(FEATURES / "hex_maestra.parquet")[["hex_id", "lat", "lon", "comuna_id"]]
    riesgo = riesgo.merge(hex_maestra, on="hex_id", how="left")

    riesgo.to_parquet(FEATURES / "riesgo_predicho.parquet", index=False)
    print(f"Guardado: riesgo_predicho.parquet, {len(riesgo):,} filas (hex×turno)")
    print(riesgo.groupby("turno", observed=True)["score_riesgo"].describe())


if __name__ == "__main__":
    main()
