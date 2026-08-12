"""
Genera `riesgo_predicho_por_tipo.parquet`: una superficie de riesgo por tipo
de delito a grano (hex_id, turno), más una combinada, para que los módulos de
Capa 2 puedan optimizar sobre el tipo que corresponda.

QUÉ TIPO ENTRA Y POR QUÉ — las decisiones salen de lo medido en
train_por_tipo.py, no de criterio a mano (ver README, "Desagregación por tipo"):

- Robo, Lesiones, Amenazas: modelo por tipo. Le ganan a su baseline naive
  (+6,4%, +9,2%, +3,7%), bastante más que el 2% del modelo agregado.
- Hurto: BASELINE HISTÓRICO, no el modelo. Se midió que el modelo es PEOR que
  el promedio histórico (MAE 0,1345 vs. 0,1319): el hurto es más estacionario
  que el resto. Usar el modelo sería ignorar nuestro propio resultado.
- Vialidad: EXCLUIDO. Son siniestros viales, no delitos de seguridad, y su
  patrón lo manda la infraestructura vial. Empata con el naive (+0,3%).
- Homicidios: EXCLUIDO. 78 hechos en todo el año de test y PEI 54% contra
  95-99,6% del resto: a este grano no hay patrón que aprender.

LA COMBINACIÓN ES UNA DECISIÓN DE POLÍTICA, NO DE MODELO
Los módulos optimizan sobre UNA superficie. Combinar seis en una exige decidir
cuánto pesa una lesión contra un robo, y eso no lo define un modelo. El default
acá es peso igual sobre superficies normalizadas (cada tipo aporta lo mismo),
que es lo único defendible sin tomar una posición: no privilegia a ninguno.
Ponderar por volumen reproduciría el modelo agregado y anularía el sentido de
desagregar. PESOS está arriba para que quien decida lo cambie en una línea.

Uso: python predecir_riesgo_por_tipo.py
"""

from __future__ import annotations

import gc
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from build_training_table_tipo import slug
from train_baseline import CATEGORICAS, FEATURES_COLS, TARGET

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
MODELS_DIR = FEATURES / "modelos"

# tipo -> cómo se estima su superficie de riesgo
FUENTE = {
    "Robo": "modelo",
    "Hurto": "historico",   # el modelo es peor que el promedio, medido
    "Lesiones": "modelo",
    "Amenazas": "modelo",
}
EXCLUIDOS = {"Vialidad": "no es delito de seguridad", "Homicidios": "no modelable a este grano"}

# peso de cada tipo en la superficie combinada. Cambiar acá si la política
# de seguridad define otra prioridad -- ver docstring.
PESOS = {"Robo": 1.0, "Hurto": 1.0, "Lesiones": 1.0, "Amenazas": 1.0}


def leer_columna(ruta: Path, nombre: str) -> pd.Series:
    arr = pq.read_table(ruta, columns=[nombre]).column(nombre).combine_chunks()
    if nombre in CATEGORICAS:
        s = arr.dictionary_encode().to_pandas()
        if s.isna().any():
            s = s.cat.add_categories(["sin_dato"]).fillna("sin_dato")
        return s
    s = arr.to_pandas()
    if s.dtype == "float64":
        return s.astype("float32")
    if s.dtype in ("int64", "int32"):
        return pd.to_numeric(s, downcast="integer")
    return s


def cargar(ruta: Path, cols: list[str], mascara: np.ndarray) -> pd.DataFrame:
    """Columna por columna y recortado a la máscara: la tabla entera no entra
    en memoria en esta máquina (ver train_incertidumbre)."""
    datos = {}
    for c in cols:
        s = leer_columna(ruta, c)
        datos[c] = s[mascara].reset_index(drop=True)
        del s
        gc.collect()
    return pd.DataFrame(datos)


def superficie_de_tipo(tipo: str) -> pd.DataFrame:
    ruta = FEATURES / f"training_table_{slug(tipo)}.parquet"
    if not ruta.exists():
        raise SystemExit(f"falta {ruta.name} — correr build_training_table_tipo.py {tipo}")

    anio = pq.read_table(ruta, columns=["fecha"]).column("fecha").to_pandas().dt.year.to_numpy()
    col = f"score_{slug(tipo)}"

    if FUENTE[tipo] == "historico":
        # promedio observado por hex×turno en train (<=2023): la misma
        # referencia que el baseline naive, que para hurto predice mejor que
        # el modelo
        df = cargar(ruta, ["hex_id", "turno", TARGET], anio <= 2023)
        sup = df.groupby(["hex_id", "turno"], observed=True)[TARGET].mean().rename(col).reset_index()
    else:
        df = cargar(ruta, FEATURES_COLS, anio == 2025)
        modelo = lgb.Booster(model_file=str(MODELS_DIR / f"modelo_{slug(tipo)}.txt"))
        pred = np.clip(modelo.predict(df[FEATURES_COLS]), 0, None)
        df["_pred"] = pred
        sup = df.groupby(["hex_id", "turno"], observed=True)["_pred"].mean().rename(col).reset_index()
        del modelo

    del df
    gc.collect()
    print(f"  {tipo:10s} ({FUENTE[tipo]:9s}): media={sup[col].mean():.4f} max={sup[col].max():.4f}")
    return sup


def main() -> None:
    print("Superficies por tipo (grano hex×turno, período 2025):")
    for tipo, motivo in EXCLUIDOS.items():
        print(f"  {tipo:10s} EXCLUIDO — {motivo}")

    combinada: pd.DataFrame | None = None
    for tipo in FUENTE:
        sup = superficie_de_tipo(tipo)
        combinada = sup if combinada is None else combinada.merge(sup, on=["hex_id", "turno"], how="outer")

    assert combinada is not None
    # solo los scores: hex_id y turno son categóricas y fillna(0) sobre una
    # categórica intenta agregar 0 como categoría nueva y explota
    for tipo in FUENTE:
        col = f"score_{slug(tipo)}"
        combinada[col] = combinada[col].fillna(0)

    # normalizar antes de combinar: las tasas difieren ~6x entre tipos, así que
    # sin normalizar "peso igual" seria en realidad "peso por volumen" y la
    # combinada colapsaria al modelo agregado
    partes = []
    for tipo, peso in PESOS.items():
        col = f"score_{slug(tipo)}"
        maximo = combinada[col].max()
        partes.append(peso * combinada[col] / maximo if maximo else combinada[col] * 0)
    combinada["score_combinado"] = sum(partes) / sum(PESOS.values())

    hex_maestra = pd.read_parquet(FEATURES / "hex_maestra.parquet")[["hex_id", "lat", "lon", "comuna_id"]]
    combinada = combinada.merge(hex_maestra, on="hex_id", how="left")

    ruta = FEATURES / "riesgo_predicho_por_tipo.parquet"
    combinada.to_parquet(ruta, index=False)
    print(f"\nGuardado: {ruta.name}, {len(combinada):,} filas (hex×turno)")

    cols = [f"score_{slug(t)}" for t in FUENTE] + ["score_combinado"]
    print("\nCorrelación de Spearman entre superficies (¿priorizan los mismos hexágonos?):")
    print(combinada[cols].corr(method="spearman").round(3).to_string())


if __name__ == "__main__":
    main()
