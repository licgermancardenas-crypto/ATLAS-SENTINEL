"""
Descarga y normaliza el dataset de Cajeros Automáticos
(data.buenosaires.gob.ar/dataset/cajeros-automaticos).

El único de este lote que viene "limpio": comma-separado, lat/lon en
columnas propias, sin coma decimal ni proyección rara.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "secretaria-de-desarrollo-urbano/cajeros-automaticos/cajeros-automaticos.csv"
)

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "cajeros" / "cajeros.csv"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def main() -> None:
    resp = requests.get(URL, timeout=60)
    resp.raise_for_status()
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_PATH.write_bytes(resp.content)

    df = pd.read_csv(RAW_PATH, encoding="utf-8-sig")
    df.columns = [c.strip().lower() for c in df.columns]

    before = len(df)
    df = df.dropna(subset=["lat", "long"])
    print(f"Cajeros: {before} -> {len(df)} tras descartar sin geolocalización")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PROCESSED_DIR / "cajeros.parquet", index=False)
    print(f"Guardado: {len(df)} filas")
    print(df["banco"].value_counts().head(10))


if __name__ == "__main__":
    main()
