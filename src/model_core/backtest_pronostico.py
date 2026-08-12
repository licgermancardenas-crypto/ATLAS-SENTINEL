"""
Evalúa el modelo semanal COMO PRONÓSTICO: validación con origen deslizante
y comparación contra persistencia.

POR QUÉ ESTE SCRIPT EXISTE
El proyecto se presenta como predictivo, pero hasta acá evaluaba con un split
fijo (train <=2023, test 2025): eso mide "qué tan bien describe el riesgo
típico", no "qué tan bien anticipa la semana que viene". Son preguntas
distintas y la segunda es la operativa.

LO QUE NO HACE FALTA CAMBIAR
El modelo ya es un pronóstico válido a un paso: todas las features dinámicas
están shifteadas al menos una semana (`shift(1)` antes del rolling, lag_1sem
incluido), así que para la fila de la semana t solo usa información hasta
t-1. No hay fuga temporal. Lo que faltaba era el PROTOCOLO de evaluación.

LAS DOS REFERENCIAS
- Promedio histórico por hex×turno: la misma de train_baseline. Mide si el
  modelo aporta algo sobre "este lugar es así".
- PERSISTENCIA (lo que pasó la semana pasada): la referencia dura en series
  de tiempo, y la que el proyecto nunca midió. Si el modelo no le gana a
  repetir la última observación, no hay señal dinámica aprovechable y
  conviene saberlo.

Se reentrena en cada origen: entrenar una vez y predecir muchas semanas
adelante mediría otra cosa (degradación del modelo), no pronóstico a un paso.

Uso: python backtest_pronostico.py [n_origenes]
"""

from __future__ import annotations

import sys
from pathlib import Path

import lightgbm as lgb
import mlflow
import numpy as np
import pandas as pd

from train_baseline import MLFLOW_TRACKING_URI, TARGET

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
TABLA = FEATURES / "training_table_semanal.parquet"

CATEGORICAS = ["hex_id", "turno", "comuna_id", "radio_censal_id", "comisaria_id", "mes"]
NUMERICAS = [
    "lag_1sem", "lag_4sem", "lag_52sem", "roll_4sem_sum", "roll_12sem_sum",
    "vecino_k1_roll4", "vecino_k2_roll4", "poblacion_hex", "pct_hogares_nbi",
    "pct_hacinamiento_critico", "n_camaras", "n_luminarias", "pct_espacio_verde",
    "semana_del_anio",
]
BOOLEANAS = ["semana_con_feriado"]
COLS = CATEGORICAS + NUMERICAS + BOOLEANAS

N_ORIGENES = 26  # medio año de orígenes semanales


def cargar() -> pd.DataFrame:
    tabla = pd.read_parquet(TABLA)
    for c in CATEGORICAS:
        tabla[c] = tabla[c].astype("category")
        if tabla[c].isna().any():
            tabla[c] = tabla[c].cat.add_categories(["sin_dato"]).fillna("sin_dato")
    for c in tabla.columns:
        if tabla[c].dtype == "float64":
            tabla[c] = tabla[c].astype("float32")
        elif tabla[c].dtype in ("int64", "int32"):
            tabla[c] = pd.to_numeric(tabla[c], downcast="integer")
    return tabla


def recall_at_k(df: pd.DataFrame, col: str, k: float = 0.20) -> float:
    """Fracción de delitos reales capturados por el top-k de hexágonos según
    la predicción. Es la métrica que de verdad importa para priorizar."""
    por_hex = df.groupby("hex_id", observed=True).agg(real=(TARGET, "sum"), pred=(col, "sum"))
    total = por_hex["real"].sum()
    if total == 0:
        return float("nan")
    top = por_hex.sort_values("pred", ascending=False).head(max(1, int(round(len(por_hex) * k))))
    return float(top["real"].sum() / total)


def main() -> None:
    n_origenes = int(sys.argv[1]) if len(sys.argv) > 1 else N_ORIGENES
    tabla = cargar()
    semanas = np.sort(tabla["semana"].unique())
    origenes = semanas[-(n_origenes + 1):-1]  # el último origen predice la última semana
    print(f"{len(tabla):,} filas | {len(semanas)} semanas | {len(origenes)} orígenes "
          f"({pd.Timestamp(origenes[0]).date()} a {pd.Timestamp(origenes[-1]).date()})")

    filas = []
    for i, origen in enumerate(origenes, 1):
        objetivo = semanas[np.searchsorted(semanas, origen) + 1]
        train = tabla[tabla["semana"] <= origen]
        test = tabla[tabla["semana"] == objetivo].copy()

        modelo = lgb.LGBMRegressor(
            # 200x31 en vez de los 500x63 de produccion: son 26 reentrenamientos
            # en una maquina de 3,4GB y la serializacion del modelo con hex_id
            # categorico (401 niveles) tiraba MemoryError. Se aplica igual en
            # todos los origenes, asi que la comparacion es consistente -- pero
            # es CONSERVADOR para el modelo: si pierde contra la persistencia,
            # hay que confirmarlo con la config completa antes de concluir.
            objective="tweedie", tweedie_variance_power=1.5, n_estimators=200,
            learning_rate=0.05, num_leaves=31, min_child_samples=50,
            random_state=42, verbose=-1,
        )
        modelo.fit(train[COLS], train[TARGET], categorical_feature=CATEGORICAS)
        test["modelo"] = np.clip(modelo.predict(test[COLS]), 0, None)

        # persistencia: lo observado la semana anterior, que para la fila de la
        # semana objetivo es exactamente lag_1sem
        test["persistencia"] = test["lag_1sem"].fillna(0)

        prom = train.groupby(["hex_id", "turno"], observed=True)[TARGET].mean()
        idx = pd.MultiIndex.from_arrays([test["hex_id"], test["turno"]])
        test["historico"] = prom.reindex(idx).fillna(train[TARGET].mean()).to_numpy()

        fila = {"origen": pd.Timestamp(origen).date().isoformat(),
                "objetivo": pd.Timestamp(objetivo).date().isoformat(),
                "delitos_reales": int(test[TARGET].sum())}
        for nombre in ("modelo", "persistencia", "historico"):
            fila[f"mae_{nombre}"] = float(np.abs(test[TARGET] - test[nombre]).mean())
            fila[f"recall20_{nombre}"] = recall_at_k(test, nombre)
        filas.append(fila)
        print(f"  [{i:2d}/{len(origenes)}] {fila['objetivo']}  "
              f"MAE modelo={fila['mae_modelo']:.4f}  persist={fila['mae_persistencia']:.4f}  "
              f"hist={fila['mae_historico']:.4f}")

    res = pd.DataFrame(filas)
    ruta = FEATURES / "backtest_pronostico.parquet"
    res.to_parquet(ruta, index=False)

    print(f"\n{'=' * 64}\nPRONÓSTICO A UNA SEMANA — {len(res)} orígenes\n{'=' * 64}")
    resumen = {}
    for nombre in ("modelo", "persistencia", "historico"):
        mae, rec = res[f"mae_{nombre}"].mean(), res[f"recall20_{nombre}"].mean()
        resumen[nombre] = (mae, rec)
        print(f"  {nombre:13s} MAE={mae:.4f}  Recall@20%={rec:.1%}")

    mae_m = resumen["modelo"][0]
    for ref in ("persistencia", "historico"):
        d = (resumen[ref][0] - mae_m) / resumen[ref][0]
        print(f"  modelo vs {ref}: {d:+.2%} de MAE")
    gana = (res["mae_modelo"] < res["mae_persistencia"]).mean()
    print(f"  el modelo le gana a la persistencia en {gana:.0%} de las semanas")

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("atlas-sentinel-modelo-nucleo")
    with mlflow.start_run(run_name="backtest-pronostico-1sem"):
        mlflow.log_params({"n_origenes": len(res), "horizonte": "1 semana",
                           "protocolo": "origen deslizante, reentrena por origen"})
        mlflow.log_metrics({f"{k}_{n}": v for n, (a, b) in resumen.items()
                            for k, v in (("mae", a), ("recall20", b))})
        mlflow.log_metric("semanas_gana_a_persistencia", gana)
    print(f"\nGuardado: {ruta.name}")


if __name__ == "__main__":
    main()
