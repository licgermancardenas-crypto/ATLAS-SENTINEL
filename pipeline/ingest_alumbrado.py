"""
Descarga y normaliza el dataset de Alumbrado LED
(data.buenosaires.gob.ar/dataset/alumbrado-led).

Un solo archivo con una fila por luminaria instalada en calles y avenidas.
Particularidad del dataset: separador ";" y coordenadas con coma decimal
("-34,554512" en vez de "-34.554512").
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "ministerio-de-espacio-publico-e-higiene-urbana/alumbrado-led/calles-y-avenidas.csv"
)

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "alumbrado" / "calles-y-avenidas.csv"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def main() -> None:
    resp = requests.get(URL, timeout=60)
    resp.raise_for_status()
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_PATH.write_bytes(resp.content)

    df = pd.read_csv(RAW_PATH, sep=";", encoding="utf-8-sig", decimal=",")
    df.columns = [c.strip().lower() for c in df.columns]

    before = len(df)
    df = df.dropna(subset=["lat", "lng"])
    df = df[(df["lat"] != 0) & (df["lng"] != 0)]
    print(f"Luminarias: {before} -> {len(df)} tras descartar sin geolocalización")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "alumbrado.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Guardado: {out_path} ({len(df)} filas)")

    print(df["comunaid"].value_counts().sort_index())


if __name__ == "__main__":
    main()
