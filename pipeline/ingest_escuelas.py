"""
Descarga y normaliza el dataset de Establecimientos Educativos
(data.buenosaires.gob.ar/dataset/establecimientos-educativos).

Las coordenadas vienen en el sistema plano legacy ("0 de Flores"), no en
GKBA ni en lat/lon directo — ver geo_utils.py para la calibración y el
margen de error (~100m).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from geo_utils import gkba_legacy_point_to_latlon

URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "ministerio-de-educacion/establecimientos-educativos/establecimientos_educativos.csv"
)

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "escuelas" / "escuelas.csv"
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
    df["lat"], df["lon"] = gkba_legacy_point_to_latlon(df["geometry"])
    df = df.drop(columns=["geometry"])
    print(f"Escuelas: {before} -> {len(df)} tras descartar sin geolocalización")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PROCESSED_DIR / "escuelas.parquet", index=False)
    print(f"Guardado: {len(df)} filas")
    print(df["nen_mde"].value_counts().head(10))


if __name__ == "__main__":
    main()
