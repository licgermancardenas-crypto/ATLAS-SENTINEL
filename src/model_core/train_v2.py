"""
Entrena el modelo núcleo v2 (con exógenas) sobre training_table_v2.parquet
y compara Recall@K contra v1 — roadmap paso 3 de arquitectura-sige-ba.pdf.
Reutiliza las funciones genéricas de train_baseline.py en vez de duplicar
la lógica de entrenamiento/métricas.
"""

from __future__ import annotations

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from train_baseline import CATEGORICAS, NUMERICAS, BOOLEANAS, TARGET, entrenar, metricas, recall_at_k

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
MODELS_DIR = FEATURES / "modelos"

NUMERICAS_V2 = NUMERICAS + ["temp_media_c"]
BOOLEANAS_V2 = BOOLEANAS + ["lluvia", "evento_en_hex", "evento_en_barrio", "cerca_estadio"]
FEATURES_COLS_V2 = CATEGORICAS + NUMERICAS_V2 + BOOLEANAS_V2


def cargar_splits_v2() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    tabla = pd.read_parquet(FEATURES / "training_table_v2.parquet")
    for col in CATEGORICAS:
        tabla[col] = tabla[col].astype("category")
    anio = tabla["fecha"].dt.year
    train, val, test = tabla[anio <= 2023], tabla[anio == 2024], tabla[anio == 2025]
    print(f"Train: {len(train):,} | Val: {len(val):,} | Test: {len(test):,}")
    return train, val, test


def main() -> None:
    train, val, test = cargar_splits_v2()
    modelo = entrenar(train, val, FEATURES_COLS_V2)

    test = test.copy()
    test["pred_v2"] = np.clip(modelo.predict(test[FEATURES_COLS_V2]), 0, None)

    print("\nMétricas en test (2025) — modelo v2 (con exógenas):")
    metricas(test[TARGET], test["pred_v2"], "LightGBM Poisson v2")

    print("\nRecall@K — modelo v2:")
    recall_at_k(test, "pred_v2", [0.05, 0.10, 0.20, 0.30])

    importancias = pd.Series(modelo.feature_importances_, index=FEATURES_COLS_V2).sort_values(ascending=False)
    print("\nImportancia de features v2:")
    print(importancias)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    modelo.booster_.save_model(str(MODELS_DIR / "modelo_nucleo_v2.txt"))
    print(f"\nModelo guardado en {MODELS_DIR / 'modelo_nucleo_v2.txt'}")


if __name__ == "__main__":
    main()
