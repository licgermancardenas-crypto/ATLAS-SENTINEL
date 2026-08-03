"""
CAPA 3 (arquitectura-sige-ba.pdf, sección 5): explicabilidad del modelo
núcleo v1 vía SHAP — "esto se explica en un 40% por historial reciente,
25% por baja iluminación, 20% por proximidad a evento masivo, etc."

Dos salidas:
1. Importancia global (media de |SHAP| por feature) — qué mueve el
   modelo en general, sobre una muestra del test 2025 (no todo el
   dataset, por RAM: TreeExplainer es exacto pero calcular SHAP para las
   585K filas de test no hace falta para una lectura global confiable).
2. Explicación local de los N hexágonos×turno con mayor riesgo predicho
   del test — el desglose por feature como % de la magnitud total de
   SHAP de esa fila, que es la forma natural de leer "esto se explica en
   x% por A, y% por B".
"""

from __future__ import annotations

import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "model_core"))
from train_baseline import CATEGORICAS, FEATURES_COLS  # noqa: E402

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
MODELS_DIR = FEATURES / "modelos"

MUESTRA_GLOBAL = 20_000
TOP_N_EXPLICAR = 5


def cargar_test_con_predicciones() -> tuple[pd.DataFrame, lgb.Booster]:
    tabla = pd.read_parquet(FEATURES / "training_table.parquet")
    for col in CATEGORICAS:
        tabla[col] = tabla[col].astype("category")
    test = tabla[tabla["fecha"].dt.year == 2025].copy()

    modelo = lgb.Booster(model_file=str(MODELS_DIR / "modelo_nucleo_v1.txt"))
    test["pred"] = np.clip(modelo.predict(test[FEATURES_COLS]), 0, None)
    return test, modelo


def main() -> None:
    test, modelo = cargar_test_con_predicciones()

    muestra = test.sample(n=min(MUESTRA_GLOBAL, len(test)), random_state=42)
    explainer = shap.TreeExplainer(modelo)
    shap_vals = explainer.shap_values(muestra[FEATURES_COLS])

    importancia_global = pd.Series(np.abs(shap_vals).mean(axis=0), index=FEATURES_COLS).sort_values(ascending=False)
    print(f"Importancia global (SHAP, muestra de {len(muestra):,} filas de test 2025):")
    print((importancia_global / importancia_global.sum() * 100).round(1).astype(str) + "%")

    print(f"\n--- Explicación local: top {TOP_N_EXPLICAR} hex×turno×fecha de mayor riesgo predicho en test ---")
    top = test.nlargest(TOP_N_EXPLICAR, "pred")
    shap_top = explainer.shap_values(top[FEATURES_COLS])

    for i, (_, fila) in enumerate(top.iterrows()):
        valores = pd.Series(shap_top[i], index=FEATURES_COLS)
        aporte_pct = (valores.abs() / valores.abs().sum() * 100).sort_values(ascending=False)
        print(f"\nhex {fila['hex_id']} | {fila['fecha'].date()} | turno {fila['turno']} "
              f"| conteo_esperado={fila['pred']:.2f} (real={fila['conteo_delitos']})")
        for feat in aporte_pct.head(4).index:
            signo = "+" if valores[feat] > 0 else "-"
            print(f"  {aporte_pct[feat]:.0f}% -> {feat} (valor={fila[feat]}, {signo} riesgo)")

    resumen = pd.DataFrame({
        "feature": FEATURES_COLS,
        "importancia_shap": importancia_global.reindex(FEATURES_COLS).to_numpy(),
    }).sort_values("importancia_shap", ascending=False)
    resumen.to_parquet(FEATURES / "shap_importancia_global.parquet", index=False)
    print(f"\nGuardado: shap_importancia_global.parquet")


if __name__ == "__main__":
    main()
