"""
Descarga y normaliza el dataset de Comisarías Policía de la Ciudad
(data.buenosaires.gob.ar/dataset/comisarias-policia-ciudad).

A diferencia de divisiones-comisarias-vecinales (que da polígonos de zona
de patrullaje), este dataset trae la ubicación PUNTUAL real de cada
comisaría, en lat/lon WGS84 normal — sin proyección local rara.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "ministerio-de-justicia-y-seguridad/comisarias-policia-ciudad/comisarias_policia.csv"
)

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "comisarias_policia" / "comisarias_policia.csv"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def main() -> None:
    resp = requests.get(URL, timeout=60)
    resp.raise_for_status()
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_PATH.write_bytes(resp.content)

    df = pd.read_csv(RAW_PATH, encoding="utf-8-sig")
    df.columns = [c.strip().lower() for c in df.columns]

    before = len(df)
    df = df.dropna(subset=["geometry"])
    coords = df["geometry"].str.extract(r"POINT \(([\-0-9\.]+) ([\-0-9\.]+)\)").astype(float)
    df["lon"], df["lat"] = coords[0], coords[1]
    df = df.drop(columns=["geometry"])
    print(f"Comisarías: {before} -> {len(df)} tras descartar sin geolocalización")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PROCESSED_DIR / "comisarias_policia.parquet", index=False)
    print(f"Guardado: {len(df)} filas")


if __name__ == "__main__":
    main()
