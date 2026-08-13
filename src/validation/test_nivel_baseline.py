"""
¿La ventaja del modelo sobre el baseline naive es priorización o es nivel?

El modelo le gana al promedio histórico 2,0% en MAE pero solo 0,7 puntos en
Recall@20%. Esa asimetría es sospechosa: el Recall@K es invariante a la escala
—solo mide si el ranking de hexágonos es bueno— mientras que el MAE castiga el
sesgo de nivel. Que se muevan tan distinto sugiere que parte de la ventaja no
es "el modelo prioriza mejor" sino "el modelo se dio cuenta de que el nivel
bajó".

Y hay motivo para sospecharlo. La serie anual de delitos:

    2016-2019  ~145.000/año
    2020        84.877   (-42%, cuarentena)
    2021       109.383   (-25%)
    2022-2024  ~148.000/año
    2025       130.421   (-16% vs 2024, con los 12 meses completos)

El baseline naive es el promedio de train (2016-2023) por hex×turno, así que
arrastra dos años de pandemia hacia abajo y tres años de nivel alto hacia
arriba, y después se lo evalúa contra un 2025 que está 16% por debajo de 2024.
El modelo tiene lags y rollings: puede seguir el nivel. El naive no puede.

Esto compara el modelo contra baselines naive que SÍ pueden seguir el nivel,
para separar las dos cosas:

  - naive_full          promedio de todo el train (el actual)
  - naive_2023          promedio del último año de train
  - naive_22_23         promedio de los dos últimos años de train
  - naive_sin_pandemia  promedio de train excluyendo 2020 y 2021
  - naive_recalibrado   naive_full reescalado por el nivel de 2024

El último es el más importante metodológicamente: mantiene EXACTAMENTE el mismo
ranking que naive_full (es una multiplicación por un escalar) y solo le corrige
el nivel, usando 2024 —el set de validación— y nunca el test. Si el modelo le
gana a naive_full pero no a naive_recalibrado, la ventaja era de nivel, porque
es el único que cambió entre los dos.

RESULTADO: la sospecha era infundada, y por un motivo que vale la pena anotar.

El promedio de los 8 años de train da ~131.800 delitos/año, y 2025 cerró en
128.429 — o sea que naive_full le pega al nivel del año de test con 2,6% de
sesgo, casi nada. Las dos distorsiones se cancelan: la pandemia tira el promedio
histórico para abajo justo lo suficiente como para que coincida con un 2025 que
también está por debajo del nivel reciente. El modelo le gana ese 2% de MAE
contra un baseline que NO tiene sesgo de nivel, así que la ventaja es real y no
es escala.

El corolario es incómodo: los dos años de pandemia son load-bearing por pura
casualidad. Sacarlos (naive_sin_pandemia) empeora el baseline de 0,2983 a
0,3075, y recalibrarlo con 2024 —que fue un año alto, justo antes de una caída
del 16%— lo empeora todavía más, a 0,3135. Es decir que el baseline contra el
que se compara todo el proyecto es, para este año de test puntual, el mejor de
las cinco variantes probadas. La comparación del README no está inflada: si
algo, es la más exigente disponible.

Y es frágil: si 2026 vuelve al nivel de ~150.000, naive_full va a subpredecir
~15% y el modelo va a parecer mucho mejor sin haber mejorado en nada. Cuando se
reentrene con 2026, hay que volver a mirar esta tabla antes de leer el MAE.

Lo que no se mueve con nada de esto es el Recall@K: las cinco variantes quedan
entre 44,7% y 45,0%, y el modelo en 45,5%. La priorización espacial es estable
sea cual sea la ventana histórica que se use — que es, otra vez, el resultado
de fondo del proyecto.

Salida: data/features/test_nivel_baseline.parquet
"""

from __future__ import annotations

import gc
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "model_core"))

from train_baseline import FEATURES_COLS, TARGET  # noqa: E402
from train_incertidumbre import FEATURES_TABLE, leer_columna_achicada  # noqa: E402

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
MODELO = FEATURES / "modelos" / "modelo_nucleo_v1.txt"
SALIDA = FEATURES / "test_nivel_baseline.parquet"

KS = [0.10, 0.20, 0.30]


# Nota sobre el orden de las categorías, porque parece un bug y no lo es.
# `leer_columna_achicada` usa dictionary_encode de arrow, que arma el
# diccionario en orden de APARICIÓN, mientras que el .astype("category") de
# pandas que usó train_baseline al entrenar los ordena. En `dia_semana` los dos
# órdenes difieren en el 100% de los códigos ([4,5,6,0,1,2,3] contra
# [0,1,...,6], porque la tabla arranca el 2016-01-01, que fue viernes), y es la
# 6ª feature por ganancia — así que parecía que el modelo iba a leer una
# categoría por otra.
#
# No pasa: el .txt del modelo guarda un bloque `pandas_categorical` con los
# VALORES de cada categoría al entrenar, y LightGBM realinea cualquier
# DataFrame con dtype categórico por valor antes de predecir. Verificado
# empíricamente: reordenar las categorías cambia el 100% de los códigos y deja
# las predicciones bit a bit idénticas. Solo habría que preocuparse si se le
# pasara un array de códigos crudo en vez de un DataFrame.


def cargar_claves() -> pd.DataFrame:
    """hex_id, turno, año y target para las 5,86M filas — las cuatro columnas
    que hacen falta para armar cualquier variante de promedio histórico. Es
    barato (~36MB) comparado con la tabla entera (~907MB)."""
    anio = pq.read_table(FEATURES_TABLE, columns=["fecha"]).column("fecha").to_pandas().dt.year
    df = pd.DataFrame({"anio": anio.astype("int16")})
    del anio
    gc.collect()
    for col in ["hex_id", "turno", TARGET]:
        df[col] = leer_columna_achicada(col)
    return df


def cargar_features_test(mascara_test: np.ndarray) -> pd.DataFrame:
    """Las 27 features, pero solo para las filas de 2025. Se lee columna por
    columna y se recorta antes de leer la siguiente, así el pico es una columna
    completa (~95MB) y no la tabla entera."""
    partes = {}
    for col in FEATURES_COLS:
        serie = leer_columna_achicada(col)
        partes[col] = serie[mascara_test].reset_index(drop=True)
        del serie
        gc.collect()
    return pd.DataFrame(partes)


def promedio_por_hex_turno(df: pd.DataFrame, mascara: np.ndarray) -> pd.Series:
    return df.loc[mascara].groupby(["hex_id", "turno"], observed=True)[TARGET].mean()


def aplicar(medias: pd.Series, test: pd.DataFrame, relleno: float) -> np.ndarray:
    pred = test.set_index(["hex_id", "turno"]).index.map(medias)
    return pd.Series(pred, index=test.index).fillna(relleno).to_numpy()


def recall_en(test: pd.DataFrame, pred: np.ndarray, k: float) -> float:
    """% de delitos reales de 2025 que caen en el top-K% de hexágonos según la
    predicción. Idéntico a train_baseline.recall_at_k, reescrito acá para poder
    pasarle un array suelto en vez de una columna del DataFrame."""
    por_hex = pd.DataFrame({"hex_id": test["hex_id"], "real": test[TARGET], "pred": pred}) \
        .groupby("hex_id", observed=True)[["real", "pred"]].sum()
    top_n = max(1, int(round(len(por_hex) * k)))
    capturado = por_hex.sort_values("pred", ascending=False)["real"].iloc[:top_n].sum()
    return capturado / por_hex["real"].sum()


def evaluar(nombre: str, test: pd.DataFrame, pred: np.ndarray) -> dict:
    y = test[TARGET].to_numpy()
    fila = {
        "variante": nombre,
        "mae": float(np.abs(y - pred).mean()),
        "rmse": float(np.sqrt(((y - pred) ** 2).mean())),
        # sesgo de nivel: >1 sobrepredice el volumen total del año de test
        "sesgo_nivel": float(pred.sum() / y.sum()),
    }
    for k in KS:
        fila[f"recall_{int(k * 100)}"] = float(recall_en(test, pred, k))
    return fila


def main() -> None:
    df = cargar_claves()
    es_train = (df["anio"] <= 2023).to_numpy()
    es_val = (df["anio"] == 2024).to_numpy()
    es_test = (df["anio"] == 2025).to_numpy()
    print(f"train {es_train.sum():,} | val {es_val.sum():,} | test {es_test.sum():,}")

    print("\nDelitos por año (suma del target, para tener el nivel a la vista):")
    por_anio = df.groupby("anio")[TARGET].sum()
    for a, v in por_anio.items():
        print(f"  {a}: {v:>9,}")

    test = df.loc[es_test].reset_index(drop=True)
    val = df.loc[es_val].reset_index(drop=True)
    media_global = df.loc[es_train, TARGET].mean()

    filas = []

    # --- el modelo de producción ---
    booster = lgb.Booster(model_file=str(MODELO))
    X_test = cargar_features_test(es_test)
    pred_modelo = np.clip(booster.predict(X_test), 0, None)
    del X_test
    gc.collect()
    filas.append(evaluar("modelo", test, pred_modelo))

    # --- variantes del promedio histórico ---
    ventanas = {
        "naive_full": es_train,
        "naive_2023": es_train & (df["anio"] == 2023).to_numpy(),
        "naive_22_23": es_train & (df["anio"] >= 2022).to_numpy(),
        "naive_sin_pandemia": es_train & (~df["anio"].isin([2020, 2021])).to_numpy(),
    }
    medias_full = None
    for nombre, mascara in ventanas.items():
        medias = promedio_por_hex_turno(df, mascara)
        if nombre == "naive_full":
            medias_full = medias
        relleno = df.loc[mascara, TARGET].mean()
        filas.append(evaluar(nombre, test, aplicar(medias, test, relleno)))

    # --- naive_full recalibrado con el nivel de 2024 ---
    # el factor sale de VAL, nunca del test: es lo que haría alguien parado a
    # fin de 2024 que ve que su promedio histórico viene sobrepredciendo.
    pred_val = aplicar(medias_full, val, media_global)
    factor = val[TARGET].sum() / pred_val.sum()
    print(f"\nFactor de recalibración estimado en 2024 (val): {factor:.4f}")
    pred_recal = aplicar(medias_full, test, media_global) * factor
    filas.append(evaluar("naive_recalibrado", test, pred_recal))

    res = pd.DataFrame(filas)
    cols = ["variante", "mae", "rmse", "sesgo_nivel"] + [f"recall_{int(k * 100)}" for k in KS]
    res = res[cols]

    mae_modelo = res.loc[res["variante"] == "modelo", "mae"].iloc[0]
    res["mejora_del_modelo_vs"] = (res["mae"] - mae_modelo) / res["mae"]

    print("\n" + "=" * 100)
    print(res.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print("=" * 100)

    res.to_parquet(SALIDA, index=False)
    print(f"\nGuardado: {SALIDA.name}")


if __name__ == "__main__":
    main()
