"""
CAPA 0, paso 3 de arquitectura-sige-ba.pdf: asigna hex_id (y turno, cuando
el dataset tiene hora) a cada dataset puntual, y guarda el resultado en
data/features/. No agrega/cuenta todavía — eso es parte de armar la tabla
de entrenamiento de Capa 1, acá solo se etiqueta cada fila cruda.

Cada dataset de origen tiene sus propias columnas de lat/lon (a veces
"latitud"/"longitud", a veces "lat"/"lng") — se declaran acá una vez por
dataset en vez de asumir un nombre común.

Cubre los 4 datasets que el documento usa como ejemplo (delitos,
siniestros, cámaras, alumbrado) más el resto de los datasets puntuales
con lat/lon directo: cajeros, comisarías (ubicación puntual), escuelas,
hospitales, universidades, estadios, eventos masivos (solo filas con
lat/lon — la mayoría de 2023-2026 no tienen, quedan sin hex_id) y las
estaciones de ecobici/molinetes.

Quedan afuera de este script (no son point-in-hex simple, son overlay de
polígono contra la grilla): espacios_verdes y comisarias.parquet (el de
zonas de patrullaje, no confundir con comisarias_policia que sí es
puntual) — fila 7 y 8 de la tabla de cruces del PDF, pendientes.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hex_utils import asignar_hex_id, turno_desde_hora

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
FEATURES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "features"

# (archivo, col_lat, col_lon, col_hora | None)
DATASETS = [
    ("delitos", "latitud", "longitud", "franja"),
    ("siniestros_hechos", "latitud_siniestro", "longitud_siniestro", "hora_siniestro"),
    ("camaras", "latitud", "longitud", None),
    ("alumbrado", "lat", "lng", None),
    ("cajeros", "lat", "long", None),
    ("comisarias_policia", "lat", "lon", None),
    ("escuelas", "lat", "lon", None),
    ("hospitales", "lat", "lon", None),
    ("universidades", "lat", "lon", None),
    ("estadios", "lat", "lon", None),
    ("eventos_masivos", "lat", "lon", None),
    ("ecobici_estaciones", "lat", "lon", None),
    ("molinetes_estaciones", "lat", "lon", None),
]


def main() -> None:
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    for nombre, col_lat, col_lon, col_hora in DATASETS:
        df = pd.read_parquet(PROCESSED_DIR / f"{nombre}.parquet")
        # No se descartan filas sin lat/lon (ej. eventos_masivos 2023-2026, que
        # solo tienen barrio) — asignar_hex_id ya deja hex_id nulo en esos casos,
        # la fila se conserva igual porque el resto de sus columnas sigue sirviendo.
        df["hex_id"] = asignar_hex_id(df, col_lat, col_lon)
        if col_hora is not None:
            df["turno"] = turno_desde_hora(df[col_hora])
        df.to_parquet(FEATURES_DIR / f"{nombre}_hex.parquet", index=False)
        con_hex = df["hex_id"].notna().sum()
        print(f"{nombre}: {len(df)} filas, {con_hex} con hex_id ({df['hex_id'].nunique()} hexágonos distintos)")


if __name__ == "__main__":
    main()
