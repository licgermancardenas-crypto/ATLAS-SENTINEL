"""
Arma una tabla de entrenamiento POR TIPO DE DELITO, sobre la misma grilla
(hex_id, fecha, turno) que la tabla agregada.

POR QUÉ
El modelo núcleo predice los 6 tipos sumados. El README lo dejó anotado como
pendiente desde v1: robo, hurto, lesiones, amenazas, vialidad y homicidios
tienen dinámicas espacio-temporales distintas, y sumarlos puede estar
diluyendo señal — un hexágono con mucho hurto diurno y otro con robo nocturno
entran al modelo como el mismo número.

QUÉ CAMBIA RESPECTO DE LA TABLA AGREGADA
Solo el target y las features que se derivan de él: conteo, lags 7/30/365,
rolling 7/30 y la vecindad espacial pasan a ser del tipo. El contexto
(socioeconómico, infraestructura, calendario) es independiente del tipo y se
calcula igual. Por eso se reusan las funciones de build_training_table.py en
vez de duplicar el pipeline: si cambia la definición de una feature, cambia
para ambas tablas a la vez.

MEMORIA
No se arma una tabla ancha de 6 targets (serían ~35M filas y esta máquina
tiene 3,4GB). Se genera y guarda UN tipo por corrida, con el mismo pico que
la tabla agregada, que ya se sabe que entra.

Uso:
    python build_training_table_tipo.py Robo
    python build_training_table_tipo.py --todos
"""

from __future__ import annotations

import gc
import sys
from pathlib import Path

import pandas as pd

from build_training_table import (
    FEATURES,
    agregar_calendario,
    agregar_lags_y_rolling,
    agregar_socioeconomico_e_infraestructura,
    agregar_vecindad_espacial,
    armar_grilla_densa,
    cargar_hexes_validos,
)

# el orden es por volumen, de mayor a menor -- ver README
TIPOS = ["Robo", "Hurto", "Lesiones", "Amenazas", "Vialidad", "Homicidios"]


def slug(tipo: str) -> str:
    return tipo.lower().replace(" ", "_")


def cargar_conteo_de_tipo(tipo: str) -> pd.DataFrame:
    """Igual que build_training_table.cargar_conteo_delitos pero filtrando por
    tipo. Se leen solo las 4 columnas necesarias: el parquet completo trae 18
    y no hacen falta."""
    df = pd.read_parquet(FEATURES / "delitos_hex.parquet", columns=["hex_id", "fecha", "turno", "tipo"])
    df = df[df["tipo"] == tipo]
    if df.empty:
        raise SystemExit(f"no hay delitos del tipo {tipo!r} — tipos válidos: {TIPOS}")
    conteo = (
        df.groupby(["hex_id", "fecha", "turno"], observed=True)
        .size()
        .reset_index(name="conteo_delitos")
    )
    conteo["conteo_delitos"] = conteo["conteo_delitos"].astype("int16")
    return conteo


def construir(tipo: str) -> Path:
    print(f"\n{'=' * 60}\n{tipo}\n{'=' * 60}")
    hexes = cargar_hexes_validos()
    hex_ids = sorted(hexes["hex_id"].tolist())

    tabla = armar_grilla_densa(hex_ids)

    conteo = cargar_conteo_de_tipo(tipo)
    print(f"Hechos del tipo: {int(conteo['conteo_delitos'].sum()):,} "
          f"en {len(conteo):,} celdas con al menos uno")
    tabla = tabla.merge(conteo, on=["hex_id", "fecha", "turno"], how="left")
    tabla["conteo_delitos"] = tabla["conteo_delitos"].fillna(0).astype("int16")
    del conteo
    gc.collect()

    print("Calculando lags/rolling del tipo...")
    tabla = agregar_lags_y_rolling(tabla)

    print("Calculando vecindad espacial (k=1, k=2) del tipo...")
    tabla = agregar_vecindad_espacial(tabla, hex_ids)

    print("Agregando socioeconómico e infraestructura...")
    tabla = agregar_socioeconomico_e_infraestructura(tabla, hexes)

    print("Agregando calendario...")
    tabla = agregar_calendario(tabla)

    ruta = FEATURES / f"training_table_{slug(tipo)}.parquet"
    tabla.to_parquet(ruta, index=False)

    ceros = (tabla["conteo_delitos"] == 0).mean()
    media = tabla["conteo_delitos"].mean()
    var = tabla["conteo_delitos"].var()
    print(f"\nGuardado: {ruta.name}, {len(tabla):,} filas")
    print(f"  media={media:.4f} | % ceros={ceros:.2%} | var/media={var / media if media else float('nan'):.2f}")
    if ceros > 0.99:
        print("  AVISO: más del 99% de las celdas en cero — a este grano el tipo"
              " puede no ser modelable; conviene mirarlo antes de entrenar.")
    del tabla
    gc.collect()
    return ruta


def main() -> None:
    args = sys.argv[1:]
    if not args:
        raise SystemExit(f"uso: python build_training_table_tipo.py <tipo>|--todos\ntipos: {TIPOS}")
    tipos = TIPOS if args[0] == "--todos" else args
    for tipo in tipos:
        construir(tipo)


if __name__ == "__main__":
    main()
