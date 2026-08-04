"""
Validación espacial (P0, ver auditoría técnica externa, sección 6) — el
documento de arquitectura original ya pedía esto ("dejar afuera un
subconjunto de hexágonos completos") y nunca se implementó. El split
temporal (train≤2023/val 2024/test 2025) solo prueba que el modelo
interpola bien en el tiempo para hexágonos que YA VIO en entrenamiento
— no dice nada sobre si generalizaría a un hexágono nuevo (una zona en
desarrollo urbano, un área sin historial confiable).

Método: separar ~20% de los 401 hexágonos válidos ANTES de entrenar
(nunca aparecen en train ni en val), entrenar de cero solo con el resto,
y comparar Recall@K/PAI/PEI del test 2025 separado en "hexágonos vistos
en entrenamiento" vs. "hexágonos nunca vistos" (holdout). La brecha
entre ambos es la medida real de cuánto generaliza el modelo más allá de
memorizar la ubicación vía hex_id/radio_censal_id — que ya sabíamos
(por SHAP e importancia de splits) que son las features dominantes.

Esto es un experimento de diagnóstico, no reemplaza al modelo de
producción (entrenar sin 20% de los hexágonos sería un desperdicio de
datos para el modelo que realmente se usa en predecir_riesgo.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "model_core"))
from train_baseline import CATEGORICAS, FEATURES_COLS, TARGET, entrenar, metricas, reportar_pai_pei  # noqa: E402

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
MODELS_DIR = FEATURES / "modelos"

FRACCION_HOLDOUT = 0.20
SEMILLA = 42


def main() -> None:
    tabla = pd.read_parquet(FEATURES / "training_table.parquet")
    for col in CATEGORICAS:
        tabla[col] = tabla[col].astype("category")

    hex_ids = sorted(tabla["hex_id"].cat.categories)
    rng = np.random.default_rng(SEMILLA)
    n_holdout = int(round(len(hex_ids) * FRACCION_HOLDOUT))
    hex_holdout = set(rng.choice(hex_ids, size=n_holdout, replace=False))
    print(f"Hexágonos holdout (nunca vistos en entrenamiento): {len(hex_holdout)} de {len(hex_ids)}")

    anio = tabla["fecha"].dt.year
    en_holdout = tabla["hex_id"].isin(hex_holdout)

    train = tabla[(anio <= 2023) & ~en_holdout]
    val = tabla[(anio == 2024) & ~en_holdout]
    test_visto = tabla[(anio == 2025) & ~en_holdout]
    test_holdout = tabla[(anio == 2025) & en_holdout]
    print(f"Train: {len(train):,} (sin hexágonos holdout) | Val: {len(val):,} | "
          f"Test visto: {len(test_visto):,} | Test holdout: {len(test_holdout):,}")

    modelo = entrenar(train, val, FEATURES_COLS)

    for nombre, test in [("HEXÁGONOS VISTOS en entrenamiento", test_visto), ("HEXÁGONOS HOLDOUT (nunca vistos)", test_holdout)]:
        test = test.copy()
        test["pred"] = np.clip(modelo.predict(test[FEATURES_COLS]), 0, None)
        print(f"\n=== {nombre} ({test['hex_id'].nunique()} hexágonos) ===")
        metricas(test[TARGET], test["pred"], "LightGBM Poisson")
        reportar_pai_pei(test, "pred", [0.10, 0.20, 0.30])

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    modelo.booster_.save_model(str(MODELS_DIR / "modelo_nucleo_spatial_holdout.txt"))
    print(f"\nModelo de diagnóstico guardado en {MODELS_DIR / 'modelo_nucleo_spatial_holdout.txt'} "
          f"(no reemplaza al modelo de producción)")


if __name__ == "__main__":
    main()
