"""
CAPA 1 (arquitectura-sige-ba.pdf, sección 3.2-3.5): entrena el modelo
núcleo v1 — LightGBM, objetivo Poisson, sobre training_table.parquet.

Validación por split temporal (no aleatorio, sección 3.4): entrena hasta
2023, valida con 2024 (early stopping), testea con 2025. Se compara
contra un baseline naive (promedio histórico del mismo hex×turno en el
período de train) y se reporta Recall@K — de los hexágonos que el modelo
marca como más riesgosos, qué % de los delitos reales del test cae ahí.
Esta es la métrica que más importa para el pitch (sección 3.4).
"""

from __future__ import annotations

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "features" / "modelos"

CATEGORICAS = ["hex_id", "turno", "comuna_id", "radio_censal_id", "comisaria_id", "dia_semana", "mes"]
NUMERICAS = [
    "lag_7d", "lag_30d", "lag_365d", "roll_7d_sum", "roll_30d_sum",
    "vecino_k1_roll30", "vecino_k2_roll30", "poblacion_hex",
    "pct_hogares_nbi", "pct_hacinamiento_critico", "n_camaras", "n_luminarias",
    "pct_espacio_verde",
]
BOOLEANAS = ["es_feriado"]
FEATURES_COLS = CATEGORICAS + NUMERICAS + BOOLEANAS
TARGET = "conteo_delitos"


def cargar_splits() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    tabla = pd.read_parquet(FEATURES / "training_table.parquet")
    for col in CATEGORICAS:
        tabla[col] = tabla[col].astype("category")

    anio = tabla["fecha"].dt.year
    train = tabla[anio <= 2023]
    val = tabla[anio == 2024]
    test = tabla[anio == 2025]
    print(f"Train: {len(train):,} filas (hasta 2023) | Val: {len(val):,} (2024) | Test: {len(test):,} (2025)")
    return train, val, test


def entrenar(train: pd.DataFrame, val: pd.DataFrame, features_cols: list[str] = FEATURES_COLS) -> lgb.LGBMRegressor:
    modelo = lgb.LGBMRegressor(
        objective="poisson",
        n_estimators=500,
        learning_rate=0.05,
        num_leaves=63,
        min_child_samples=50,
        random_state=42,
        verbose=-1,
    )
    modelo.fit(
        train[features_cols], train[TARGET],
        eval_set=[(val[features_cols], val[TARGET])],
        eval_metric="poisson",
        callbacks=[lgb.early_stopping(30, verbose=False)],
        categorical_feature=[c for c in CATEGORICAS if c in features_cols],
    )
    print(f"Mejor iteración: {modelo.best_iteration_}")
    return modelo


def baseline_naive(train: pd.DataFrame, eval_df: pd.DataFrame) -> pd.Series:
    """Promedio histórico de train, mismo hex×turno."""
    medias = train.groupby(["hex_id", "turno"], observed=True)[TARGET].mean()
    pred = eval_df.set_index(["hex_id", "turno"]).index.map(medias)
    return pd.Series(pred, index=eval_df.index).fillna(train[TARGET].mean())


def metricas(y_true: pd.Series, y_pred: np.ndarray, nombre: str) -> None:
    mae = np.abs(y_true - y_pred).mean()
    rmse = np.sqrt(((y_true - y_pred) ** 2).mean())
    print(f"  {nombre}: MAE={mae:.4f}  RMSE={rmse:.4f}")


def recall_at_k(test: pd.DataFrame, pred_col: str, ks: list[float]) -> None:
    """% de delitos reales del test que caen en el top-K% de hexágonos
    según riesgo total predicho (sumado sobre todo el período de test)."""
    por_hex = test.groupby("hex_id", observed=True).agg(
        real=(TARGET, "sum"), predicho=(pred_col, "sum")
    ).sort_values("predicho", ascending=False)
    total_real = por_hex["real"].sum()
    n_hex = len(por_hex)
    print(f"  Recall@K (sobre {n_hex} hexágonos, {total_real:,} delitos reales en test):")
    for k in ks:
        top_n = max(1, int(round(n_hex * k)))
        capturado = por_hex["real"].iloc[:top_n].sum()
        print(f"    top {k:.0%} de hexágonos ({top_n}) -> {capturado / total_real:.1%} de los delitos reales")


def pai_pei(test: pd.DataFrame, pred_col: str, k: float) -> tuple[float, float]:
    """Predictive Accuracy Index / Predictive Efficiency Index (Chainey,
    Tompson & Uhlig 2008) — el estándar de la literatura de hotspot
    policing, lo que hace estos resultados comparables contra papers
    publicados en vez de solo contra el propio baseline.

    PAI = (delitos capturados / delitos totales) / (área usada / área total).
    Con hexágonos H3 de área casi idéntica entre sí, área_usada/área_total
    ≈ k (fracción de hexágonos elegidos) — PAI ≈ Recall@k / k: "cuántas
    veces mejor que marcar hexágonos al azar".

    PEI = PAI del modelo / PAI del mejor mapa de hotspots posible con el
    mismo k (rankeando por el delito REAL del propio período de test, en
    vez de por el riesgo predicho — el techo teórico con total hindsight).
    PEI cercano a 1.0 = el modelo está cerca de lo mejor que se puede
    hacer a esa resolución; PEI bajo = hay margen real de mejora, no solo
    ruido irreducible.
    """
    por_hex = test.groupby("hex_id", observed=True).agg(real=(TARGET, "sum"), predicho=(pred_col, "sum"))
    total_real = por_hex["real"].sum()
    n_hex = len(por_hex)
    top_n = max(1, int(round(n_hex * k)))

    capturado_modelo = por_hex.sort_values("predicho", ascending=False)["real"].iloc[:top_n].sum()
    capturado_hindsight = por_hex.sort_values("real", ascending=False)["real"].iloc[:top_n].sum()

    pai_modelo = (capturado_modelo / total_real) / k
    pai_hindsight = (capturado_hindsight / total_real) / k
    pei = pai_modelo / pai_hindsight if pai_hindsight > 0 else float("nan")
    return pai_modelo, pei


def reportar_pai_pei(test: pd.DataFrame, pred_col: str, ks: list[float]) -> None:
    print(f"  PAI / PEI (Chainey et al. 2008):")
    for k in ks:
        pai, pei = pai_pei(test, pred_col, k)
        print(f"    k={k:.0%}: PAI={pai:.2f} (x veces mejor que azar) | PEI={pei:.1%} (vs. techo con hindsight)")


def main() -> None:
    train, val, test = cargar_splits()
    modelo = entrenar(train, val)

    test = test.copy()
    test["pred_modelo"] = np.clip(modelo.predict(test[FEATURES_COLS]), 0, None)
    test["pred_naive"] = baseline_naive(train, test)

    print("\nMétricas en test (2025):")
    metricas(test[TARGET], test["pred_modelo"], "LightGBM Poisson")
    metricas(test[TARGET], test["pred_naive"], "Baseline naive (media hist. hex×turno)")

    print("\nRecall@K — modelo:")
    recall_at_k(test, "pred_modelo", [0.05, 0.10, 0.20, 0.30])
    print("\nRecall@K — baseline naive:")
    recall_at_k(test, "pred_naive", [0.05, 0.10, 0.20, 0.30])

    print("\nPAI/PEI — modelo:")
    reportar_pai_pei(test, "pred_modelo", [0.10, 0.20, 0.30])

    importancias = pd.Series(modelo.feature_importances_, index=FEATURES_COLS).sort_values(ascending=False)
    print("\nImportancia de features (ganancia de splits):")
    print(importancias)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    modelo.booster_.save_model(str(MODELS_DIR / "modelo_nucleo_v1.txt"))
    print(f"\nModelo guardado en {MODELS_DIR / 'modelo_nucleo_v1.txt'}")


if __name__ == "__main__":
    main()
