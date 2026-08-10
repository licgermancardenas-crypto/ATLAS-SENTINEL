"""
P1 de la auditoría técnica externa (sección 2): dos deudas del modelo
núcleo v1 medidas y nunca corregidas — sobredispersión real (varianza/
media = 1,59 sobre conteo_delitos, medida en la auditoría; Poisson
asume razón 1,0) y cero cuantificación de incertidumbre (el pipeline
emite un solo número puntual, sin banda de confianza, para un sistema
que alimenta asignación de recursos públicos).

Dos piezas, misma corrida:

1. Objetivo Tweedie (compound Poisson-Gamma, `tweedie_variance_power`
   entre 1 y 2) en vez de Poisson puro — LightGBM lo soporta nativo, es
   el análogo práctico a Binomial Negativa disponible sin salir del
   mismo framework de gradient boosting (NB pura no tiene objetivo
   nativo en LightGBM; Tweedie es la alternativa estándar de la
   industria de seguros/conteos para sobredispersión, ver Jørgensen
   1997). Se compara punto a punto contra Poisson con las mismas
   métricas (MAE, PAI/PEI) para decidir si vale reemplazar al modelo de
   producción.

2. Regresión cuantílica (p10/p50/p90) — mismas features, mismo split,
   `objective="quantile"` con alpha 0.1/0.5/0.9. Se valida con cobertura
   empírica: si el intervalo [p10,p90] está bien calibrado, ~80% de los
   valores reales de test deberían caer adentro. Esto no reemplaza al
   modelo de producción — es la banda de incertidumbre que Módulo A
   necesitaría para optimización robusta (auditoría, sección 7), un
   paso futuro que queda habilitado por esto pero no implementado acá.
"""

from __future__ import annotations

import gc
from pathlib import Path

import lightgbm as lgb
import mlflow
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from train_baseline import (
    CATEGORICAS, FEATURES_COLS, MLFLOW_TRACKING_URI, TARGET,
    metricas, reportar_pai_pei,
)

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
MODELS_DIR = FEATURES / "modelos"

FEATURES_TABLE = FEATURES / "training_table.parquet"
TWEEDIE_VARIANCE_POWER = 1.5


def leer_columna_achicada(nombre: str) -> pd.Series:
    """Lee UNA columna del parquet y la devuelve ya en su dtype chico.

    Las categóricas se codifican con dictionary_encode de pyarrow en vez de
    leerlas a object y hacer .astype("category") en pandas: hex_id son 5,86M
    strings de 15 caracteres, que como array de objetos pesa ~350MB antes de
    que pandas pueda achicarlo. En arrow el diccionario se arma en la lectura
    y a pandas ya llega como Categorical (401 categorías + codes int16, ~12MB).
    """
    arr = pq.read_table(FEATURES_TABLE, columns=[nombre]).column(nombre).combine_chunks()
    if nombre in CATEGORICAS:
        serie = arr.dictionary_encode().to_pandas()
        del arr
        # radio_censal_id tiene NaN (hexes sin radio asignado) -- misma razón
        # que train_baseline.sacar_nan_categoricas: un código -1 promueve el
        # array combinado de LightGBM a float64 y tira abajo el float32 de
        # TODAS las columnas, no solo de esa.
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


def cargar_splits_lean() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Loader propio, columna por columna, en vez de train_baseline.cargar_splits.

    cargar_splits lee el parquet entero a pandas con los dtypes del archivo
    (float64/int64/object: ~1,4GB para 5,86M x 29 filas) y recién ahí achica.
    Ese pico no entra en esta máquina de 3,4GB cuando quedan <600MB libres: la
    corrida murió con ArrayMemoryError pidiendo 45MB dentro de achicar_floats,
    con la tabla cruda ya en memoria.

    Acá se lee una sola columna por vez, se la achica y se la parte en los tres
    splits antes de leer la siguiente — el pico pasa a ser (splits acumulados,
    ~550MB) + (una columna, ~95MB) en vez de la tabla cruda entera. Las
    categorías se arman sobre la columna COMPLETA y se cortan después, así los
    tres splits comparten el mismo dtype categórico; si cada split armara sus
    propias categorías, LightGBM codificaría distinto train y test.

    Los splits salen recortados a FEATURES_COLS+TARGET (sin 'fecha'): acá no se
    usan recall_at_k ni nada que necesite el resto de las columnas, y pai_pei
    solo agrupa por hex_id, que ya es feature.
    """
    anio = pq.read_table(FEATURES_TABLE, columns=["fecha"]).column("fecha").to_pandas().dt.year.to_numpy()
    mascaras = {"train": anio <= 2023, "val": anio == 2024, "test": anio == 2025}
    del anio
    gc.collect()

    partes: dict[str, dict[str, pd.Series]] = {nombre: {} for nombre in mascaras}
    for col in FEATURES_COLS + [TARGET]:
        serie = leer_columna_achicada(col)
        for nombre, mascara in mascaras.items():
            partes[nombre][col] = serie[mascara].reset_index(drop=True)
        del serie
        gc.collect()

    train, val, test = (pd.DataFrame(partes.pop(nombre)) for nombre in ("train", "val", "test"))
    gc.collect()
    print(f"Train: {len(train):,} | Val: {len(val):,} | Test: {len(test):,}")
    return train, val, test


def entrenar_tweedie(
    X_train: pd.DataFrame, y_train: pd.Series, X_val: pd.DataFrame, y_val: pd.Series
) -> lgb.LGBMRegressor:
    modelo = lgb.LGBMRegressor(
        objective="tweedie", tweedie_variance_power=TWEEDIE_VARIANCE_POWER,
        n_estimators=500, learning_rate=0.05, num_leaves=63, min_child_samples=50,
        random_state=42, verbose=-1,
    )
    modelo.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        eval_metric="tweedie",
        callbacks=[lgb.early_stopping(30, verbose=False)],
        categorical_feature=CATEGORICAS,
    )
    print(f"Tweedie — mejor iteración: {modelo.best_iteration_}")
    return modelo


def entrenar_cuantil(train: pd.DataFrame, val: pd.DataFrame, alpha: float) -> lgb.LGBMRegressor:
    modelo = lgb.LGBMRegressor(
        objective="quantile", alpha=alpha,
        n_estimators=500, learning_rate=0.05, num_leaves=63, min_child_samples=50,
        random_state=42, verbose=-1,
    )
    modelo.fit(
        train[FEATURES_COLS], train[TARGET],
        eval_set=[(val[FEATURES_COLS], val[TARGET])],
        eval_metric="quantile",
        callbacks=[lgb.early_stopping(30, verbose=False)],
        categorical_feature=CATEGORICAS,
    )
    print(f"Cuantil {alpha} — mejor iteración: {modelo.best_iteration_}")
    return modelo


def main() -> None:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("atlas-sentinel-modelo-nucleo")

    with mlflow.start_run(run_name="incertidumbre-tweedie-cuantiles"):
        train, val, test = cargar_splits_lean()
        mlflow.log_params({
            "variante": "incertidumbre", "n_filas_train": len(train), "n_filas_test": len(test),
            "tweedie_variance_power": TWEEDIE_VARIANCE_POWER,
        })

        print("=== Tweedie vs. Poisson (sobredispersión) ===")
        # se extraen X/y y se libera train/val antes del fit -> pico ~1,2GB en
        # vez de ~1,8GB (máquina de 3,4GB). Ver train_v2/entrenar_xy.
        X_tr, y_tr = train[FEATURES_COLS], train[TARGET]
        X_val, y_val = val[FEATURES_COLS], val[TARGET]
        del train, val
        gc.collect()
        modelo_tweedie = entrenar_tweedie(X_tr, y_tr, X_val, y_val)
        del X_tr, y_tr, X_val, y_val
        gc.collect()
        test["pred_tweedie"] = np.clip(modelo_tweedie.predict(test[FEATURES_COLS]), 0, None)
        m = metricas(test[TARGET], test["pred_tweedie"], "LightGBM Tweedie")
        pp = reportar_pai_pei(test, "pred_tweedie", [0.10, 0.20, 0.30])
        mlflow.log_params({"mejor_iteracion_tweedie": modelo_tweedie.best_iteration_})
        mlflow.log_metrics({f"tweedie_{k}": v for k, v in {**m, **pp}.items()})

        modelo_tweedie.booster_.save_model(str(MODELS_DIR / "modelo_nucleo_tweedie.txt"))

        # p10/p50/p90 ya se reentrenaron post-fix de turno en conformal_prediction.py
        # (con el mismo entrenar_cuantil) -- se reusan en vez de re-entrenar acá para
        # no encadenar 4 entrenamientos pesados en el mismo proceso (esta máquina de
        # 3,4GB ya mostró que eso mata el proceso por memoria).
        print("\n=== Regresión cuantílica (p10 / p50 / p90) -- reusando modelos ya frescos ===")
        preds_cuantil = {}
        for alpha in [0.1, 0.5, 0.9]:
            ruta = MODELS_DIR / f"modelo_nucleo_p{int(alpha*100)}.txt"
            modelo_q = lgb.Booster(model_file=str(ruta))
            preds_cuantil[alpha] = np.clip(modelo_q.predict(test[FEATURES_COLS]), 0, None)

        test["p10"] = preds_cuantil[0.1]
        test["p50"] = preds_cuantil[0.5]
        test["p90"] = preds_cuantil[0.9]

        # p10 debería ser <= p90 por construcción del boosting, pero los tres
        # modelos son independientes — puede cruzarse en algún punto ("quantile
        # crossing", problema conocido de la regresión cuantílica no conjunta).
        cruces = int((test["p10"] > test["p90"]).sum())
        print(f"\nFilas con p10 > p90 (quantile crossing): {cruces} de {len(test):,} ({cruces/len(test):.2%})")

        cobertura = ((test[TARGET] >= test["p10"]) & (test[TARGET] <= test["p90"])).mean()
        print(f"Cobertura empírica del intervalo [p10,p90]: {cobertura:.1%} (objetivo: ~80%)")

        ancho_medio = (test["p90"] - test["p10"]).mean()
        print(f"Ancho medio del intervalo: {ancho_medio:.3f} delitos esperados")

        mlflow.log_metrics({
            "quantile_crossing": cruces,
            "cobertura_p10_p90": float(cobertura),
            "ancho_medio_intervalo": float(ancho_medio),
        })

        print("\nAncho del intervalo por nivel de riesgo (p50), en cuartiles:")
        # p50 está muy sesgado a cero (misma dispersión que conteo_delitos, ver
        # README) — qcut sobre el valor crudo colapsa bins duplicados y falla
        # con las etiquetas; se cuantiliza sobre el rank (siempre valores
        # únicos) en vez del valor.
        test["cuartil_p50"] = pd.qcut(
            test["p50"].rank(method="first"), 4, labels=["bajo", "medio-bajo", "medio-alto", "alto"]
        )
        test["ancho_intervalo"] = test["p90"] - test["p10"]
        test["dentro_intervalo"] = (test[TARGET] >= test["p10"]) & (test[TARGET] <= test["p90"])
        print(test.groupby("cuartil_p50", observed=True).agg(
            ancho_medio=("ancho_intervalo", "mean"),
            cobertura=("dentro_intervalo", "mean"),
        ))

        print(f"\nModelos guardados en {MODELS_DIR}")


if __name__ == "__main__":
    main()
