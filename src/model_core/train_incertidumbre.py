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

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from train_baseline import CATEGORICAS, FEATURES_COLS, TARGET, cargar_splits, metricas, reportar_pai_pei

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
MODELS_DIR = FEATURES / "modelos"

TWEEDIE_VARIANCE_POWER = 1.5


def entrenar_tweedie(train: pd.DataFrame, val: pd.DataFrame) -> lgb.LGBMRegressor:
    modelo = lgb.LGBMRegressor(
        objective="tweedie", tweedie_variance_power=TWEEDIE_VARIANCE_POWER,
        n_estimators=500, learning_rate=0.05, num_leaves=63, min_child_samples=50,
        random_state=42, verbose=-1,
    )
    modelo.fit(
        train[FEATURES_COLS], train[TARGET],
        eval_set=[(val[FEATURES_COLS], val[TARGET])],
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
    train, val, test = cargar_splits()
    test = test.copy()

    print("=== Tweedie vs. Poisson (sobredispersión) ===")
    modelo_tweedie = entrenar_tweedie(train, val)
    test["pred_tweedie"] = np.clip(modelo_tweedie.predict(test[FEATURES_COLS]), 0, None)
    metricas(test[TARGET], test["pred_tweedie"], "LightGBM Tweedie")
    reportar_pai_pei(test, "pred_tweedie", [0.10, 0.20, 0.30])

    modelo_tweedie.booster_.save_model(str(MODELS_DIR / "modelo_nucleo_tweedie.txt"))

    print("\n=== Regresión cuantílica (p10 / p50 / p90) ===")
    preds_cuantil = {}
    for alpha in [0.1, 0.5, 0.9]:
        modelo_q = entrenar_cuantil(train, val, alpha)
        preds_cuantil[alpha] = np.clip(modelo_q.predict(test[FEATURES_COLS]), 0, None)
        modelo_q.booster_.save_model(str(MODELS_DIR / f"modelo_nucleo_p{int(alpha*100)}.txt"))

    test["p10"] = preds_cuantil[0.1]
    test["p50"] = preds_cuantil[0.5]
    test["p90"] = preds_cuantil[0.9]

    # p10 debería ser <= p90 por construcción del boosting, pero los tres
    # modelos son independientes — puede cruzarse en algún punto ("quantile
    # crossing", problema conocido de la regresión cuantílica no conjunta).
    cruces = (test["p10"] > test["p90"]).sum()
    print(f"\nFilas con p10 > p90 (quantile crossing): {cruces} de {len(test):,} ({cruces/len(test):.2%})")

    cobertura = ((test[TARGET] >= test["p10"]) & (test[TARGET] <= test["p90"])).mean()
    print(f"Cobertura empírica del intervalo [p10,p90]: {cobertura:.1%} (objetivo: ~80%)")

    ancho_medio = (test["p90"] - test["p10"]).mean()
    print(f"Ancho medio del intervalo: {ancho_medio:.3f} delitos esperados")

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
