"""
CAPA 1 (arquitectura-sige-ba.pdf, sección 3.2-3.5): entrena el modelo
núcleo v1 — LightGBM, objetivo Tweedie, sobre training_table.parquet.

Objetivo Tweedie, no Poisson (cambio P1 de la auditoría técnica): se
midió sobredispersión real en conteo_delitos (varianza/media = 1,59,
Poisson asume 1,0). train_incertidumbre.py compara ambos — Tweedie da
MAE/PAI/PEI iguales o levemente mejores, se adopta por corrección
estadística, no porque haya movido las métricas.

Validación por split temporal (no aleatorio, sección 3.4): entrena hasta
2023, valida con 2024 (early stopping), testea con 2025. Se compara
contra un baseline naive (promedio histórico del mismo hex×turno en el
período de train) y se reporta Recall@K, y PAI/PEI (Chainey, Tompson &
Uhlig 2008 — estándar de la literatura de hotspot policing, hace el
resultado comparable contra papers publicados).

P2 de la auditoría técnica externa (sección 10): cada corrida se registra
en MLflow local (`mlruns/` en la raíz del repo, cero infraestructura
nueva) — params, métricas y el modelo entrenado como artifact. Antes de
esto, comparar v1/v2/semanal/Tweedie era prosa a mano en el README; ahora
queda además como historial consultable con `mlflow ui`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import lightgbm as lgb
import mlflow
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent.parent
FEATURES = RAIZ / "data" / "features"
MODELS_DIR = RAIZ / "data" / "features" / "modelos"
# MLflow 3.x dejó en modo mantenimiento el backend de filesystem plano
# ("./mlruns" sin más) — pide backend de base de datos. sqlite es la
# opción más liviana que sigue siendo "cero infraestructura nueva" (un
# solo archivo local, sin server).
MLFLOW_TRACKING_URI = f"sqlite:///{(RAIZ / 'mlflow.db').as_posix()}"

CATEGORICAS = ["hex_id", "turno", "comuna_id", "radio_censal_id", "comisaria_id", "dia_semana", "mes"]
NUMERICAS = [
    "lag_7d", "lag_30d", "lag_365d", "roll_7d_sum", "roll_30d_sum",
    "vecino_k1_roll30", "vecino_k2_roll30", "poblacion_hex",
    "pct_hogares_nbi", "pct_hacinamiento_critico", "n_camaras", "n_luminarias",
    "pct_espacio_verde",
    "n_escuelas_cerca", "n_hospitales_cerca", "n_universidades_cerca", "n_cajeros_cerca",
    "flujo_ecobici", "flujo_molinetes",
]
BOOLEANAS = ["es_feriado"]
FEATURES_COLS = CATEGORICAS + NUMERICAS + BOOLEANAS
TARGET = "conteo_delitos"


def cargar_splits() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    tabla = pd.read_parquet(FEATURES / "training_table.parquet")
    for col in CATEGORICAS:
        tabla[col] = tabla[col].astype("category")
    # downcast ANTES del split -- el split por máscara booleana ya necesita
    # copiar bloques enteros, y sobre la tabla sin achicar (1,28GB en
    # float64/int64) eso alcanza para tirar ArrayMemoryError por sí solo
    # en esta máquina de 3,4GB de RAM (ver README, 'La restricción real').
    tabla = achicar_floats(tabla)
    tabla = sacar_nan_categoricas(tabla)

    anio = tabla["fecha"].dt.year
    train = tabla[anio <= 2023]
    val = tabla[anio == 2024]
    test = tabla[anio == 2025]
    print(f"Train: {len(train):,} filas (hasta 2023) | Val: {len(val):,} (2024) | Test: {len(test):,} (2025)")
    return train, val, test


def achicar_floats(df: pd.DataFrame) -> pd.DataFrame:
    """LightGBM convierte train[features_cols] a un único array float64
    homogéneo antes de entrenar (~965MB para 4,69M filas x 27 columnas) --
    en una máquina de 3,4GB de RAM eso alcanza para tirar ArrayMemoryError
    por sí solo, aparte del tamaño del DataFrame ya en memoria. float32
    alcanza de sobra para features de conteo/ratio (mismo ajuste que
    agregar_exogenas.py, ver README)."""
    # ojo: select_dtypes() consolida bloques internamente (otra copia grande
    # en memoria) -- se recorre dtypes columna por columna para evitarlo.
    for c in df.columns:
        if df[c].dtype == "float64":
            df[c] = df[c].astype("float32")
        # np.result_type(int64/int32, float32) = float64 -- un solo int64
        # (conteos de POIs cercanos) también arrastra todo el array a
        # float64, igual que el float64 de arriba.
        elif df[c].dtype in ("int64", "int32"):
            df[c] = pd.to_numeric(df[c], downcast="integer")
    return df


def sacar_nan_categoricas(df: pd.DataFrame) -> pd.DataFrame:
    """radio_censal_id tiene NaN (73.060 filas, hexes sin radio asignado).
    LightGBM codifica categorías como cat.codes con -1 para NaN, y
    Series.replace({-1: np.nan}) sobre una columna con -1 la sube a
    float64 -- eso arrastra TODO el array combinado a float64 vía
    np.result_type() (basic.py::_data_from_pandas), tirando abajo el
    downcast a float32 de arriba para las 27 columnas juntas, no solo
    para esa. Se rellena con una categoría explícita "sin_dato" antes de
    entrenar para que el código nunca sea -1."""
    for c in df.columns:
        if isinstance(df[c].dtype, pd.CategoricalDtype) and df[c].isna().any():
            df[c] = df[c].cat.add_categories(["sin_dato"]).fillna("sin_dato")
    return df


def entrenar_xy(
    X_train: pd.DataFrame, y_train: pd.Series,
    X_val: pd.DataFrame, y_val: pd.Series,
    features_cols: list[str] = FEATURES_COLS,
) -> lgb.LGBMRegressor:
    """Igual que entrenar() pero recibe X/y ya separados. Sirve para que el
    caller pueda liberar la tabla de train completa ANTES del fit: si no, en la
    máquina de 3,4GB coexisten la tabla (~620MB), el slice train[features_cols]
    (~600MB) y la matriz C de LightGBM (~600MB) = ~1,8GB de pico y el proceso
    muere por OOM al construir el Dataset. Pasando X/y y borrando la tabla, el
    pico baja a ~1,2GB (solo X pandas + matriz C)."""
    # Tweedie, no Poisson puro: la auditoría técnica midió sobredispersión real
    # en conteo_delitos (varianza/media = 1,59; Poisson asume 1,0). Comparado
    # en train_incertidumbre.py, Tweedie da MAE/PAI/PEI iguales o levemente
    # mejores que Poisson — se adopta como objetivo de producción por
    # corrección estadística, no porque haya movido las métricas.
    modelo = lgb.LGBMRegressor(
        objective="tweedie",
        tweedie_variance_power=1.5,
        n_estimators=500,
        learning_rate=0.05,
        num_leaves=63,
        min_child_samples=50,
        random_state=42,
        verbose=-1,
    )
    modelo.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        eval_metric="tweedie",
        callbacks=[lgb.early_stopping(30, verbose=False)],
        categorical_feature=[c for c in CATEGORICAS if c in features_cols],
    )
    print(f"Mejor iteración: {modelo.best_iteration_}")
    return modelo


def entrenar(train: pd.DataFrame, val: pd.DataFrame, features_cols: list[str] = FEATURES_COLS) -> lgb.LGBMRegressor:
    return entrenar_xy(train[features_cols], train[TARGET], val[features_cols], val[TARGET], features_cols)


def baseline_naive(train: pd.DataFrame, eval_df: pd.DataFrame) -> pd.Series:
    """Promedio histórico de train, mismo hex×turno."""
    medias = train.groupby(["hex_id", "turno"], observed=True)[TARGET].mean()
    pred = eval_df.set_index(["hex_id", "turno"]).index.map(medias)
    return pd.Series(pred, index=eval_df.index).fillna(train[TARGET].mean())


def metricas(y_true: pd.Series, y_pred: np.ndarray, nombre: str) -> dict[str, float]:
    mae = np.abs(y_true - y_pred).mean()
    rmse = np.sqrt(((y_true - y_pred) ** 2).mean())
    print(f"  {nombre}: MAE={mae:.4f}  RMSE={rmse:.4f}")
    return {"mae": mae, "rmse": rmse}


def recall_at_k(test: pd.DataFrame, pred_col: str, ks: list[float]) -> dict[str, float]:
    """% de delitos reales del test que caen en el top-K% de hexágonos
    según riesgo total predicho (sumado sobre todo el período de test)."""
    por_hex = test.groupby("hex_id", observed=True).agg(
        real=(TARGET, "sum"), predicho=(pred_col, "sum")
    ).sort_values("predicho", ascending=False)
    total_real = por_hex["real"].sum()
    n_hex = len(por_hex)
    print(f"  Recall@K (sobre {n_hex} hexágonos, {total_real:,} delitos reales en test):")
    resultado = {}
    for k in ks:
        top_n = max(1, int(round(n_hex * k)))
        capturado = por_hex["real"].iloc[:top_n].sum()
        recall = capturado / total_real
        print(f"    top {k:.0%} de hexágonos ({top_n}) -> {recall:.1%} de los delitos reales")
        resultado[f"recall_{int(k * 100)}"] = recall
    return resultado


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


def reportar_pai_pei(test: pd.DataFrame, pred_col: str, ks: list[float]) -> dict[str, float]:
    print(f"  PAI / PEI (Chainey et al. 2008):")
    resultado = {}
    for k in ks:
        pai, pei = pai_pei(test, pred_col, k)
        print(f"    k={k:.0%}: PAI={pai:.2f} (x veces mejor que azar) | PEI={pei:.1%} (vs. techo con hindsight)")
        resultado[f"pai_{int(k * 100)}"] = pai
        resultado[f"pei_{int(k * 100)}"] = pei
    return resultado


def git_commit_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, text=True, timeout=5
        ).strip()
    except Exception:
        return "desconocido"


def main() -> None:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("atlas-sentinel-modelo-nucleo")

    with mlflow.start_run(run_name="v1-tweedie"):
        train, val, test = cargar_splits()
        modelo = entrenar(train, val)

        mlflow.log_params({
            "objective": "tweedie", "tweedie_variance_power": 1.5,
            "n_estimators": 500, "learning_rate": 0.05, "num_leaves": 63,
            "min_child_samples": 50, "mejor_iteracion": modelo.best_iteration_,
            "n_features": len(FEATURES_COLS), "n_filas_train": len(train),
            "git_commit": git_commit_sha(),
        })

        test = test.copy()
        test["pred_modelo"] = np.clip(modelo.predict(test[FEATURES_COLS]), 0, None)
        test["pred_naive"] = baseline_naive(train, test)

        print("\nMétricas en test (2025):")
        m_modelo = metricas(test[TARGET], test["pred_modelo"], "LightGBM Poisson")
        m_naive = metricas(test[TARGET], test["pred_naive"], "Baseline naive (media hist. hex×turno)")

        print("\nRecall@K — modelo:")
        r_modelo = recall_at_k(test, "pred_modelo", [0.05, 0.10, 0.20, 0.30])
        print("\nRecall@K — baseline naive:")
        r_naive = recall_at_k(test, "pred_naive", [0.05, 0.10, 0.20, 0.30])

        print("\nPAI/PEI — modelo:")
        pp_modelo = reportar_pai_pei(test, "pred_modelo", [0.10, 0.20, 0.30])

        mlflow.log_metrics({f"modelo_{k}": v for k, v in {**m_modelo, **r_modelo, **pp_modelo}.items()})
        mlflow.log_metrics({f"naive_{k}": v for k, v in {**m_naive, **r_naive}.items()})

        importancias = pd.Series(modelo.feature_importances_, index=FEATURES_COLS).sort_values(ascending=False)
        print("\nImportancia de features (ganancia de splits):")
        print(importancias)

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        ruta_modelo = MODELS_DIR / "modelo_nucleo_v1.txt"
        modelo.booster_.save_model(str(ruta_modelo))
        print(f"\nModelo guardado en {ruta_modelo}")
        mlflow.log_artifact(str(ruta_modelo))
        mlflow.log_text(importancias.to_string(), "importancia_features.txt")

        print(f"\nCorrida registrada en MLflow — 'mlflow ui --backend-store-uri {mlflow.get_tracking_uri()}' para ver el dashboard")


if __name__ == "__main__":
    main()
