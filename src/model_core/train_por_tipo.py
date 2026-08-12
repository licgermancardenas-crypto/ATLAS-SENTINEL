"""
Entrena un modelo por tipo de delito y los compara contra el modelo agregado.

LA PREGUNTA
El modelo núcleo predice los 6 tipos sumados. ¿Se pierde señal al mezclarlos?
Robo y hurto son el 78% de los hechos, pero lesiones, amenazas y vialidad
tienen otra dinámica — y homicidios es tan raro que probablemente no se pueda
modelar a este grano. Este script lo mide en vez de suponerlo.

QUÉ COMPARA
Para cada tipo, contra su propio baseline naive (promedio histórico del hex y
turno, la misma referencia que usa train_baseline). Comparar el MAE entre
tipos no dice nada: un tipo con media 0,004 tiene MAE bajo por ser raro, no
por estar bien predicho. Lo comparable es cuánto le gana cada modelo a su
propio baseline, y el PAI/PEI, que mide concentración y es adimensional.

MEMORIA
Un tipo por vez, con el loader columna por columna de train_incertidumbre
(esta máquina tiene 3,4GB y la tabla cruda no entra). Cada modelo se guarda y
la tabla se libera antes de pasar al siguiente.

Uso:
    python train_por_tipo.py            # todos los que tengan tabla
    python train_por_tipo.py Robo Hurto
"""

from __future__ import annotations

import gc
import sys
from pathlib import Path

import lightgbm as lgb
import mlflow
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from build_training_table_tipo import TIPOS, slug
from train_baseline import (
    CATEGORICAS, FEATURES_COLS, MLFLOW_TRACKING_URI, TARGET,
    metricas, reportar_pai_pei,
)

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
MODELS_DIR = FEATURES / "modelos"
TWEEDIE_VARIANCE_POWER = 1.5


def leer_columna_achicada(ruta: Path, nombre: str) -> pd.Series:
    """Una columna por vez, en su dtype chico. Misma técnica que
    train_incertidumbre.cargar_splits_lean: leer el parquet entero y achicar
    después no entra en memoria en esta máquina."""
    arr = pq.read_table(ruta, columns=[nombre]).column(nombre).combine_chunks()
    if nombre in CATEGORICAS:
        serie = arr.dictionary_encode().to_pandas()
        del arr
        if serie.isna().any():
            serie = serie.cat.add_categories(["sin_dato"]).fillna("sin_dato")
        return serie
    serie = arr.to_pandas()
    del arr
    if serie.dtype == "float64":
        serie = serie.astype("float32")
    elif serie.dtype in ("int64", "int32"):
        serie = pd.to_numeric(serie, downcast="integer")
    return serie


def cargar_splits(ruta: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    anio = pq.read_table(ruta, columns=["fecha"]).column("fecha").to_pandas().dt.year.to_numpy()
    mascaras = {"train": anio <= 2023, "val": anio == 2024, "test": anio == 2025}
    del anio
    gc.collect()

    partes: dict[str, dict[str, pd.Series]] = {k: {} for k in mascaras}
    for col in FEATURES_COLS + [TARGET]:
        serie = leer_columna_achicada(ruta, col)
        for k, m in mascaras.items():
            partes[k][col] = serie[m].reset_index(drop=True)
        del serie
        gc.collect()
    return tuple(pd.DataFrame(partes.pop(k)) for k in ("train", "val", "test"))


def baseline_naive(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Promedio histórico por hex×turno — la misma referencia de train_baseline.
    Es el número contra el que hay que juzgar: el MAE crudo entre tipos no es
    comparable porque las tasas base difieren en dos órdenes de magnitud."""
    prom = train.groupby(["hex_id", "turno"], observed=True)[TARGET].mean()
    idx = pd.MultiIndex.from_arrays([test["hex_id"], test["turno"]])
    return prom.reindex(idx).fillna(train[TARGET].mean()).to_numpy()


def entrenar_tipo(tipo: str) -> dict | None:
    ruta = FEATURES / f"training_table_{slug(tipo)}.parquet"
    if not ruta.exists():
        print(f"  {tipo}: falta {ruta.name} — correr build_training_table_tipo.py")
        return None

    print(f"\n{'=' * 60}\n{tipo}\n{'=' * 60}")
    train, val, test = cargar_splits(ruta)

    tasa = train[TARGET].mean()
    ceros = (train[TARGET] == 0).mean()
    print(f"train: {len(train):,} filas | tasa={tasa:.4f} | ceros={ceros:.2%}")

    X_tr, y_tr = train[FEATURES_COLS], train[TARGET]
    X_val, y_val = val[FEATURES_COLS], val[TARGET]
    naive = baseline_naive(train, test)
    del train, val
    gc.collect()

    modelo = lgb.LGBMRegressor(
        objective="tweedie", tweedie_variance_power=TWEEDIE_VARIANCE_POWER,
        n_estimators=500, learning_rate=0.05, num_leaves=63, min_child_samples=50,
        random_state=42, verbose=-1,
    )
    modelo.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], eval_metric="tweedie",
               callbacks=[lgb.early_stopping(30, verbose=False)], categorical_feature=CATEGORICAS)
    del X_tr, y_tr, X_val, y_val
    gc.collect()

    test = test.copy()
    test["pred"] = np.clip(modelo.predict(test[FEATURES_COLS]), 0, None)
    test["naive"] = naive

    m = metricas(test[TARGET], test["pred"], f"{tipo} — modelo")
    mn = metricas(test[TARGET], test["naive"], f"{tipo} — baseline naive")
    pp = reportar_pai_pei(test, "pred", [0.10, 0.20, 0.30])

    mejora = (mn["mae"] - m["mae"]) / mn["mae"] if mn["mae"] else float("nan")
    print(f"  mejora sobre el baseline: {mejora:+.2%}")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    modelo.booster_.save_model(str(MODELS_DIR / f"modelo_{slug(tipo)}.txt"))

    fila = {
        "tipo": tipo, "tasa_train": tasa, "pct_ceros": ceros,
        "mae": m["mae"], "rmse": m["rmse"], "mae_naive": mn["mae"],
        "mejora_vs_naive": mejora, "mejor_iteracion": modelo.best_iteration_,
        **{k: v for k, v in pp.items()},
    }
    del test, modelo
    gc.collect()
    return fila


def main() -> None:
    tipos = sys.argv[1:] or TIPOS
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("atlas-sentinel-modelo-nucleo")

    filas = []
    for tipo in tipos:
        with mlflow.start_run(run_name=f"tipo-{slug(tipo)}"):
            fila = entrenar_tipo(tipo)
            if fila is None:
                continue
            mlflow.log_params({"tipo": tipo, "variante": "por_tipo",
                               "mejor_iteracion": fila["mejor_iteracion"]})
            mlflow.log_metrics({k: v for k, v in fila.items()
                                if isinstance(v, (int, float)) and k != "mejor_iteracion"})
            filas.append(fila)

    if not filas:
        return
    resumen = pd.DataFrame(filas)
    ruta = FEATURES / "comparacion_por_tipo.parquet"
    resumen.to_parquet(ruta, index=False)

    print(f"\n{'=' * 60}\nRESUMEN\n{'=' * 60}")
    cols = ["tipo", "tasa_train", "pct_ceros", "mae", "mae_naive", "mejora_vs_naive", "pai_10", "pei_10"]
    print(resumen[cols].to_string(index=False))
    print(f"\nGuardado: {ruta.name}")


if __name__ == "__main__":
    main()
