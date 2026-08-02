"""
Descarga y normaliza el dataset de Universidades
(data.buenosaires.gob.ar/dataset/universidades).

A diferencia de escuelas/hospitales, acá el WKT POINT viene en WGS84
normal (grados), no en el sistema plano legacy — no hace falta reproyectar.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-educacion/universidades/universidades.csv"

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "universidades" / "universidades.csv"
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
    print(f"Universidades: {before} -> {len(df)} tras descartar sin geolocalización")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PROCESSED_DIR / "universidades.parquet", index=False)
    print(f"Guardado: {len(df)} filas")
    print("rango lat:", df["lat"].min(), df["lat"].max(), "| lon:", df["lon"].min(), df["lon"].max())


if __name__ == "__main__":
    main()
