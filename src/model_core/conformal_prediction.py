"""
Corrige la deuda que train_incertidumbre.py dejó documentada explícita:
la regresión cuantílica (p10/p50/p90) da cobertura empírica de ~95% para
el intervalo [p10,p90] contra un objetivo nominal de ~80% -- los tres
modelos se entrenan de forma independiente, sin restricción conjunta, y
eso los deja sobre-calibrados (intervalos más anchos de lo que deberían).
La auditoría técnica señalaba **conformal prediction** como la corrección
real: garantías de cobertura finitas y model-agnostic, en vez de confiar
en que el propio LightGBM cuantílico ya viene bien calibrado.

Método: Conformalized Quantile Regression (CQR, Romano, Patterson & Candès
2019), simétrico y asimétrico (Q_lo/Q_hi por separado), calibrado sobre
val (2024, nunca visto por p10/p90 salvo en early stopping) y evaluado
sobre test (2025).

**Resultado real: ambas variantes dan Q=0 -- no corrigen nada, y no es un
bug.** `conteo_delitos` es >80% cero, así que el modelo p10 converge en 1
sola iteración (el p10 real de esa distribución ES cero en casi todo
lado) y el score de no-conformidad queda con una masa densa pegada a 0
-- el nivel de cuantil que pide un intervalo de 80-90% cae adentro de ese
bloque de empates, así que no hay corrección aditiva de un solo paso que
angoste el intervalo sin romper la garantía de cobertura mínima. Detalle
completo y los números en el README (sección "Conformal prediction").
Documentado como límite real del método en este dominio, no como
pendiente.

Val y test son años distintos (2024 vs 2025), no verdaderamente
intercambiables -- la garantía de cobertura marginal de conformal
prediction asume exchangeability, que acá es una aproximación práctica
(la misma que ya usa el resto del proyecto para el split temporal), no
una garantía estadística estricta. Documentado como limitación honesta,
no escondida.
"""

from __future__ import annotations

import gc
from pathlib import Path

import lightgbm as lgb
import mlflow
import numpy as np
import pandas as pd

from train_baseline import CATEGORICAS, FEATURES_COLS, MLFLOW_TRACKING_URI, TARGET, cargar_splits
from train_incertidumbre import entrenar_cuantil

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
MODELS_DIR = FEATURES / "modelos"

ALPHA = 0.2  # objetivo de cobertura: 1 - alpha = 80%


def obtener_modelo_cuantil(alpha: float, nombre_archivo: str, train: pd.DataFrame, val: pd.DataFrame) -> lgb.Booster:
    """Entrenar sobre las 4,69M filas de train es la parte más pesada de
    este script en RAM (máquina de 3,4GB -- ver README, 'La restricción
    real'), y entrenar 2-3 modelos cuantílicos en la misma corrida mata el
    proceso por memoria más de una vez seguida. Si ya hay un modelo
    guardado más nuevo que training_table.parquet, se reusa en vez de
    reentrenar -- verificado que un Booster recargado de disco predice
    idéntico (diff exacto 0.0) al modelo recién entrenado en el mismo
    proceso, así que no es una aproximación, es el mismo modelo."""
    ruta = MODELS_DIR / nombre_archivo
    tabla_mtime = (FEATURES / "training_table.parquet").stat().st_mtime
    if ruta.exists() and ruta.stat().st_mtime > tabla_mtime:
        print(f"Reusando modelo ya entrenado (post-fix de turno): {nombre_archivo}")
        return lgb.Booster(model_file=str(ruta))
    print(f"Entrenando modelo cuantil alpha={alpha} -> {nombre_archivo}")
    modelo = entrenar_cuantil(train, val, alpha)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    modelo.booster_.save_model(str(ruta))
    return modelo.booster_


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


def _cuantil_finito(scores: np.ndarray, alpha: float) -> float:
    n = len(scores)
    nivel = min(1.0, np.ceil((n + 1) * (1 - alpha)) / n)
    return float(np.quantile(scores, nivel, method="higher"))


def calibrar_conformal(p10_cal: np.ndarray, p90_cal: np.ndarray, y_cal: pd.Series, alpha: float) -> float:
    scores = np.maximum(p10_cal - y_cal.to_numpy(), y_cal.to_numpy() - p90_cal)
    return _cuantil_finito(scores, alpha)


def calibrar_conformal_asimetrico(
    p10_cal: np.ndarray, p90_cal: np.ndarray, y_cal: pd.Series, alpha: float
) -> tuple[float, float]:
    """CQR simétrico usa un solo score max(p10-y, y-p90) -- con >80% de
    conteo_delitos en cero y p10~0 (el modelo de cuantil 0.1 converge en 1
    iteración: el p10 real de una distribución 82,8% cero ES cero en casi
    todo lado), ese score empata en exactamente 0 para la mayoría de filas,
    y el cuantil 80 del score queda pegado en 0 -- no hay forma de que la
    corrección achique el intervalo sin romper cobertura del lado de abajo,
    que ya está al límite. Separar la corrección por lado (Q_lo con su
    propio presupuesto de error, Q_hi con el suyo) deja que el lado de
    arriba (p90, donde vive todo el ancho real del intervalo) se corrija
    independiente del lado de abajo, que no tiene nada para corregir."""
    scores_lo = p10_cal - y_cal.to_numpy()
    scores_hi = y_cal.to_numpy() - p90_cal
    Q_lo = _cuantil_finito(scores_lo, alpha / 2)
    Q_hi = _cuantil_finito(scores_hi, alpha / 2)
    return Q_lo, Q_hi


def cobertura_y_ancho(y: pd.Series, lo: np.ndarray, hi: np.ndarray) -> tuple[float, float]:
    cobertura = ((y >= lo) & (y <= hi)).mean()
    ancho = (hi - lo).mean()
    return cobertura, ancho


def reportar_por_cuartil(test: pd.DataFrame, p50: np.ndarray, lo: np.ndarray, hi: np.ndarray, etiqueta: str) -> None:
    df = pd.DataFrame({
        "cuartil_p50": pd.qcut(pd.Series(p50).rank(method="first"), 4, labels=["bajo", "medio-bajo", "medio-alto", "alto"]),
        "ancho": hi - lo,
        "dentro": (test[TARGET].to_numpy() >= lo) & (test[TARGET].to_numpy() <= hi),
    })
    print(f"\nAncho y cobertura por cuartil de riesgo ({etiqueta}):")
    print(df.groupby("cuartil_p50", observed=True).agg(ancho_medio=("ancho", "mean"), cobertura=("dentro", "mean")))


def main() -> None:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("atlas-sentinel-modelo-nucleo")

    with mlflow.start_run(run_name="conformal-cqr"):
        train, val, test = cargar_splits()
        train, val, test = achicar_floats(train), achicar_floats(val), achicar_floats(test)
        train, val, test = sacar_nan_categoricas(train), sacar_nan_categoricas(val), sacar_nan_categoricas(test)

        n_train = len(train)
        modelo_p10 = obtener_modelo_cuantil(0.1, "modelo_nucleo_p10.txt", train, val)
        modelo_p90 = obtener_modelo_cuantil(0.9, "modelo_nucleo_p90.txt", train, val)
        modelo_p50 = obtener_modelo_cuantil(0.5, "modelo_nucleo_p50.txt", train, val)
        del train
        gc.collect()

        p10_val = np.clip(modelo_p10.predict(val[FEATURES_COLS]), 0, None)
        p90_val = np.clip(modelo_p90.predict(val[FEATURES_COLS]), 0, None)
        p10_test = np.clip(modelo_p10.predict(test[FEATURES_COLS]), 0, None)
        p90_test = np.clip(modelo_p90.predict(test[FEATURES_COLS]), 0, None)
        p50_test = np.clip(modelo_p50.predict(test[FEATURES_COLS]), 0, None)

        cobertura_cruda, ancho_crudo = cobertura_y_ancho(test[TARGET], p10_test, p90_test)
        print(f"\nIntervalo crudo [p10,p90] en test: cobertura={cobertura_cruda:.1%}, ancho medio={ancho_crudo:.3f}")

        print("\n=== Calibrando conformal (CQR) sobre val (2024) ===")
        Q = calibrar_conformal(p10_val, p90_val, val[TARGET], ALPHA)
        print(f"Corrección Q = {Q:+.4f} delitos esperados (nivel objetivo {1 - ALPHA:.0%})")

        lo_conformal = np.clip(p10_test - Q, 0, None)
        hi_conformal = p90_test + Q

        cobertura_conformal, ancho_conformal = cobertura_y_ancho(test[TARGET], lo_conformal, hi_conformal)
        print(f"Intervalo conformalizado [p10-Q, p90+Q] en test: cobertura={cobertura_conformal:.1%}, ancho medio={ancho_conformal:.3f}")

        print("\n=== Calibrando conformal asimétrico (Q_lo, Q_hi por separado) ===")
        Q_lo, Q_hi = calibrar_conformal_asimetrico(p10_val, p90_val, val[TARGET], ALPHA)
        print(f"Q_lo = {Q_lo:+.4f} | Q_hi = {Q_hi:+.4f} (cada uno con presupuesto de error {ALPHA / 2:.0%})")

        lo_asim = np.clip(p10_test - Q_lo, 0, None)
        hi_asim = np.clip(p90_test + Q_hi, lo_asim, None)

        cobertura_asim, ancho_asim = cobertura_y_ancho(test[TARGET], lo_asim, hi_asim)
        print(f"Intervalo asimétrico [p10-Q_lo, p90+Q_hi] en test: cobertura={cobertura_asim:.1%}, ancho medio={ancho_asim:.3f}")

        reportar_por_cuartil(test, p50_test, p10_test, p90_test, "crudo")
        reportar_por_cuartil(test, p50_test, lo_conformal, hi_conformal, "conformal simétrico")
        reportar_por_cuartil(test, p50_test, lo_asim, hi_asim, "conformal asimétrico")

        mlflow.log_params({"alpha": ALPHA, "n_train": n_train, "n_cal_val": len(val), "n_test": len(test)})
        mlflow.log_metrics({
            "Q_correccion": Q,
            "Q_lo": Q_lo, "Q_hi": Q_hi,
            "cobertura_cruda": cobertura_cruda,
            "cobertura_conformal": cobertura_conformal,
            "cobertura_asimetrico": cobertura_asim,
            "ancho_crudo": ancho_crudo,
            "ancho_conformal": ancho_conformal,
            "ancho_asimetrico": ancho_asim,
        })

        resultado = test[["hex_id", "fecha", "turno", TARGET]].copy()
        resultado["p50"] = p50_test
        resultado["p10_crudo"], resultado["p90_crudo"] = p10_test, p90_test
        resultado["lo_conformal"], resultado["hi_conformal"] = lo_conformal, hi_conformal
        resultado["lo_asimetrico"], resultado["hi_asimetrico"] = lo_asim, hi_asim
        resultado.to_parquet(FEATURES / "conformal_test.parquet", index=False)

        print(f"\nGuardado: conformal_test.parquet en {FEATURES}")
        if Q == 0 and Q_lo == 0 and Q_hi == 0:
            print("Q/Q_lo/Q_hi dieron 0 -- CQR no corrige nada acá (masa de scores pegada a 0 por el "
                  "zero-inflation de conteo_delitos, ver docstring del módulo). No es un bug: es el "
                  "límite real de una corrección aditiva de un solo paso en este dominio.")


if __name__ == "__main__":
    main()
