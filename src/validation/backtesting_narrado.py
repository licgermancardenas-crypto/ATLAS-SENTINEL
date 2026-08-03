"""
CAPA 3 (arquitectura-sige-ba.pdf, sección 5): backtesting narrado +
métricas de evolución mensual + curva de calibración, todo sobre el test
2025 (fuera de entrenamiento) del modelo núcleo v1.

- Backtesting narrado: un mes real, contado como si el modelo se hubiera
  corrido "el día antes" — total real vs. predicho, y qué tan bien el
  ranking de hexágonos de ese mes concentra los delitos reales.
- Evolución mes a mes: Recall@20% y MAE por cada uno de los 12 meses de
  test — para ver si el modelo es estable o si hay meses donde se cae.
- Curva de calibración: por decil de riesgo predicho, ¿el promedio real
  coincide con el promedio predicho? (un modelo bien calibrado debería
  tener puntos cerca de la diagonal).
"""

from __future__ import annotations

import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "model_core"))
from train_baseline import CATEGORICAS, FEATURES_COLS, TARGET  # noqa: E402

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
MODELS_DIR = FEATURES / "modelos"

MES_BACKTEST = "2025-06"


def cargar_test_con_predicciones() -> pd.DataFrame:
    tabla = pd.read_parquet(FEATURES / "training_table.parquet")
    for col in CATEGORICAS:
        tabla[col] = tabla[col].astype("category")
    test = tabla[tabla["fecha"].dt.year == 2025].copy()
    modelo = lgb.Booster(model_file=str(MODELS_DIR / "modelo_nucleo_v1.txt"))
    test["pred"] = np.clip(modelo.predict(test[FEATURES_COLS]), 0, None)
    return test


def backtesting_narrado(test: pd.DataFrame) -> None:
    mes = test[test["fecha"].dt.strftime("%Y-%m") == MES_BACKTEST]
    por_hex = mes.groupby("hex_id", observed=True).agg(real=(TARGET, "sum"), predicho=("pred", "sum"))
    por_hex = por_hex.sort_values("predicho", ascending=False)

    total_real = por_hex["real"].sum()
    total_predicho = por_hex["predicho"].sum()
    top20 = por_hex.head(int(round(len(por_hex) * 0.2)))

    print(f"=== Backtesting narrado: {MES_BACKTEST} ===")
    print(f"Delitos reales en el mes: {total_real:,.0f} | suma de conteo_esperado del modelo: {total_predicho:,.0f}")
    print(f"El modelo marcó el top 20% de hexágonos ({len(top20)} de {len(por_hex)}) como los de mayor riesgo.")
    print(f"Ahí ocurrieron {top20['real'].sum():,.0f} delitos reales -> {top20['real'].sum() / total_real:.1%} del total del mes, "
          f"concentrado en el 20% del área.")
    print("\nTop 5 hexágonos marcados como más riesgosos ese mes (predicho vs. real):")
    print(por_hex.head(5).assign(diferencia=lambda d: d["real"] - d["predicho"]).round(1))


def evolucion_mensual(test: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for mes, grupo in test.groupby(test["fecha"].dt.to_period("M")):
        por_hex = grupo.groupby("hex_id", observed=True).agg(real=(TARGET, "sum"), predicho=("pred", "sum"))
        por_hex = por_hex.sort_values("predicho", ascending=False)
        top20 = por_hex.head(int(round(len(por_hex) * 0.2)))
        mae = (grupo[TARGET] - grupo["pred"]).abs().mean()
        filas.append({
            "mes": str(mes), "mae": mae,
            "recall_20pct": top20["real"].sum() / por_hex["real"].sum() if por_hex["real"].sum() > 0 else np.nan,
            "delitos_reales": por_hex["real"].sum(),
        })
    evolucion = pd.DataFrame(filas)
    print("\n=== Evolución mensual (test 2025) ===")
    print(evolucion.to_string(index=False))
    print(f"\nRecall@20% — media: {evolucion['recall_20pct'].mean():.1%}, "
          f"desvío: {evolucion['recall_20pct'].std():.1%} (estabilidad mes a mes)")
    return evolucion


def curva_calibracion(test: pd.DataFrame) -> pd.DataFrame:
    test = test.copy()
    test["decil"] = pd.qcut(test["pred"], 10, labels=False, duplicates="drop")
    calibracion = test.groupby("decil").agg(
        pred_medio=("pred", "mean"), real_medio=(TARGET, "mean"), n=(TARGET, "size"),
    ).reset_index()
    print("\n=== Calibración por decil de riesgo predicho ===")
    print(calibracion.to_string(index=False))
    return calibracion


def main() -> None:
    test = cargar_test_con_predicciones()
    backtesting_narrado(test)
    evolucion = evolucion_mensual(test)
    calibracion = curva_calibracion(test)

    evolucion.to_parquet(FEATURES / "evolucion_mensual.parquet", index=False)
    calibracion.to_parquet(FEATURES / "calibracion.parquet", index=False)
    print("\nGuardado: evolucion_mensual.parquet, calibracion.parquet")


if __name__ == "__main__":
    main()
