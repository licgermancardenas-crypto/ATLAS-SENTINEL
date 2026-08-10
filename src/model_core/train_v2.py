"""
Entrena el modelo núcleo v2 (con exógenas) sobre training_table_v2.parquet
y compara Recall@K contra v1 — roadmap paso 3 de arquitectura-sige-ba.pdf.
Reutiliza las funciones genéricas de train_baseline.py en vez de duplicar
la lógica de entrenamiento/métricas.
"""

from __future__ import annotations

import gc
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd

from train_baseline import (
    CATEGORICAS, NUMERICAS, BOOLEANAS, TARGET, MLFLOW_TRACKING_URI,
    achicar_floats, entrenar_xy, metricas, recall_at_k, reportar_pai_pei, sacar_nan_categoricas,
)

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
MODELS_DIR = FEATURES / "modelos"

NUMERICAS_V2 = NUMERICAS + ["temp_media_c"]
BOOLEANAS_V2 = BOOLEANAS + ["lluvia", "evento_en_hex", "evento_en_barrio", "cerca_estadio"]
FEATURES_COLS_V2 = CATEGORICAS + NUMERICAS_V2 + BOOLEANAS_V2


def cargar_splits_v2() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    tabla = pd.read_parquet(FEATURES / "training_table_v2.parquet")
    for col in CATEGORICAS:
        tabla[col] = tabla[col].astype("category")
    # downcast + relleno de NaN categóricas antes del split -- máquina de
    # 3,4GB, mismo motivo que train_baseline.cargar_splits (sin esto el split
    # y el entrenamiento revientan por promoción a float64). Ver achicar_floats.
    tabla = achicar_floats(tabla)
    tabla = sacar_nan_categoricas(tabla)
    anio = tabla["fecha"].dt.year
    # train/val solo se usan para fit -> se recortan a las columnas del modelo
    # y se .copy() para DESACOPLAR del parent, así se puede liberar la tabla
    # completa (~500-700MB) antes de que LightGBM aloque su propia matriz. En
    # 3,4GB de RAM (a veces <500MB libres) ese pico duplicado es lo que crashea
    # la construcción del Dataset (access violation a nivel C). test conserva
    # todas las columnas porque recall_at_k/pai_pei las necesitan.
    cols_fit = FEATURES_COLS_V2 + [TARGET]
    train = tabla.loc[anio <= 2023, cols_fit].copy()
    val = tabla.loc[anio == 2024, cols_fit].copy()
    test = tabla[anio == 2025].copy()
    del tabla
    gc.collect()
    print(f"Train: {len(train):,} | Val: {len(val):,} | Test: {len(test):,}")
    return train, val, test


def main() -> None:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("atlas-sentinel-modelo-nucleo")

    with mlflow.start_run(run_name="v2-exogenas"):
        train, val, test = cargar_splits_v2()
        # se extraen X/y y se liberan train/val antes del fit -- baja el pico de
        # RAM de ~1,8GB a ~1,2GB (ver entrenar_xy). Sin esto el proceso muere por
        # OOM al construir el Dataset en la máquina de 3,4GB.
        n_filas_train = len(train)
        X_tr, y_tr = train[FEATURES_COLS_V2], train[TARGET]
        X_val, y_val = val[FEATURES_COLS_V2], val[TARGET]
        del train, val
        gc.collect()
        modelo = entrenar_xy(X_tr, y_tr, X_val, y_val, FEATURES_COLS_V2)
        del X_tr, y_tr, X_val, y_val
        gc.collect()
        mlflow.log_params({"n_features": len(FEATURES_COLS_V2), "n_filas_train": n_filas_train,
                            "mejor_iteracion": modelo.best_iteration_, "variante": "v2_exogenas"})

        test = test.copy()
        test["pred_v2"] = np.clip(modelo.predict(test[FEATURES_COLS_V2]), 0, None)

        print("\nMétricas en test (2025) — modelo v2 (con exógenas):")
        m = metricas(test[TARGET], test["pred_v2"], "LightGBM Tweedie v2")

        print("\nRecall@K — modelo v2:")
        r = recall_at_k(test, "pred_v2", [0.05, 0.10, 0.20, 0.30])

        print("\nPAI/PEI — modelo v2:")
        pp = reportar_pai_pei(test, "pred_v2", [0.10, 0.20, 0.30])

        mlflow.log_metrics({f"modelo_{k}": v for k, v in {**m, **r, **pp}.items()})

        importancias = pd.Series(modelo.feature_importances_, index=FEATURES_COLS_V2).sort_values(ascending=False)
        print("\nImportancia de features v2:")
        print(importancias)

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        ruta_modelo = MODELS_DIR / "modelo_nucleo_v2.txt"
        modelo.booster_.save_model(str(ruta_modelo))
        print(f"\nModelo guardado en {ruta_modelo}")
        mlflow.log_artifact(str(ruta_modelo))


if __name__ == "__main__":
    main()
