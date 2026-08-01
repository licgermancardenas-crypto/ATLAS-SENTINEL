"""
Descarga y normaliza el dataset de Delitos CABA (data.buenosaires.gob.ar/dataset/delitos).

Une todos los años disponibles en un único parquet, homogeneiza nombres de columnas
(el dataset original cambia levemente de esquema entre años) y descarta filas sin
geolocalización válida.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import requests

BASE_URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "ministerio-de-justicia-y-seguridad/delitos/delitos_{year}.csv"
)
YEARS = range(2016, 2026)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "delitos"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

# El dataset publica los mismos campos con variantes de nombre entre años
# (ej. "anio"/"año", "id-mapa"/"id_mapa"). Se normalizan acá.
COLUMN_ALIASES = {
    "año": "anio",
    "id-mapa": "id_mapa",
    "id mapa": "id_mapa",
}

REQUIRED_COLUMNS = [
    "id_mapa",
    "anio",
    "mes",
    "dia",
    "fecha",
    "franja",
    "tipo",
    "subtipo",
    "uso_arma",
    "uso_moto",
    "barrio",
    "comuna",
    "latitud",
    "longitud",
    "cantidad",
]


def download_year(year: int) -> pd.DataFrame:
    url = BASE_URL.format(year=year)
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    raw_path = RAW_DIR / f"delitos_{year}.csv"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(resp.content)

    df = pd.read_csv(io.BytesIO(resp.content))
    df = df.rename(columns={c: COLUMN_ALIASES.get(c.strip().lower(), c.strip().lower()) for c in df.columns})
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Año {year}: faltan columnas esperadas: {missing}")

    df["anio_archivo"] = year
    return df[REQUIRED_COLUMNS + ["anio_archivo"]]


def main() -> None:
    frames = []
    for year in YEARS:
        print(f"Descargando {year}...")
        try:
            frames.append(download_year(year))
        except requests.HTTPError as exc:
            print(f"  saltado ({exc})")

    full = pd.concat(frames, ignore_index=True)

    before = len(full)
    full = full.dropna(subset=["latitud", "longitud"])
    full = full[(full["latitud"] != 0) & (full["longitud"] != 0)]
    after = len(full)
    print(f"Filas totales: {before} -> {after} tras descartar sin geolocalización")

    full["fecha"] = pd.to_datetime(full["fecha"], errors="coerce")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "delitos.parquet"
    full.to_parquet(out_path, index=False)
    print(f"Guardado: {out_path} ({len(full)} filas)")

    print(full["tipo"].value_counts())
    print(full["anio_archivo"].value_counts().sort_index())


if __name__ == "__main__":
    main()
