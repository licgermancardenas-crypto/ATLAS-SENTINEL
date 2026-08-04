"""
Entrena el modelo núcleo sobre training_table_semanal.parquet y compara
contra el modelo diario (v1) — ¿agregar por semana revela señal dinámica
que el grano diario, muy disperso, no dejaba ver? Reutiliza las funciones
genéricas de train_baseline.py (entrenar/métricas/recall_at_k).

Recall@K acá es sobre delitos-por-semana en vez de delitos-por-día — no
es directamente comparable número contra número con el Recall@K diario
(otro denominador temporal), pero la comparación de MAE relativo al
baseline naive, y la importancia de features, sí lo son.
"""

from __future__ import annotations

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from train_baseline import TARGET, entrenar, metricas, recall_at_k, baseline_naive

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
MODELS_DIR = FEATURES / "modelos"

CATEGORICAS = ["hex_id", "turno", "comuna_id", "radio_censal_id", "comisaria_id", "semana_del_anio", "mes"]
NUMERICAS = [
    "lag_1sem", "lag_4sem", "lag_52sem", "roll_4sem_sum", "roll_12sem_sum",
    "vecino_k1_roll4", "vecino_k2_roll4", "poblacion_hex",
    "pct_hogares_nbi", "pct_hacinamiento_critico", "n_camaras", "n_luminarias",
    "pct_espacio_verde",
]
BOOLEANAS = ["semana_con_feriado"]
FEATURES_COLS = CATEGORICAS + NUMERICAS + BOOLEANAS


def cargar_splits() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    tabla = pd.read_parquet(FEATURES / "training_table_semanal.parquet")
    for col in CATEGORICAS:
        tabla[col] = tabla[col].astype("category")
    anio = tabla["semana"].dt.year
    train, val, test = tabla[anio <= 2023], tabla[anio == 2024], tabla[anio == 2025]
    print(f"Train: {len(train):,} | Val: {len(val):,} | Test: {len(test):,}")
    return train, val, test


def main() -> None:
    train, val, test = cargar_splits()
    modelo = entrenar(train, val, FEATURES_COLS)

    test = test.copy()
    test["pred_modelo"] = np.clip(modelo.predict(test[FEATURES_COLS]), 0, None)
    test["pred_naive"] = baseline_naive(train, test)

    print("\nMétricas en test (2025), grano semanal:")
    metricas(test[TARGET], test["pred_modelo"], "LightGBM Poisson semanal")
    metricas(test[TARGET], test["pred_naive"], "Baseline naive (media hist. hex×turno)")

    print("\nRecall@K — modelo semanal:")
    recall_at_k(test, "pred_modelo", [0.05, 0.10, 0.20, 0.30])
    print("\nRecall@K — baseline naive:")
    recall_at_k(test, "pred_naive", [0.05, 0.10, 0.20, 0.30])

    importancias = pd.Series(modelo.feature_importances_, index=FEATURES_COLS).sort_values(ascending=False)
    print("\nImportancia de features (semanal):")
    print(importancias)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    modelo.booster_.save_model(str(MODELS_DIR / "modelo_nucleo_semanal.txt"))
    print(f"\nModelo guardado en {MODELS_DIR / 'modelo_nucleo_semanal.txt'}")


if __name__ == "__main__":
    main()
