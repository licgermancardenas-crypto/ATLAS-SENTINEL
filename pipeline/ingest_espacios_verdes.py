"""
Descarga y normaliza el dataset de Espacios Verdes Públicos
(data.buenosaires.gob.ar/dataset/espacios-verdes).

Son polígonos (plazas, parques, plazoletas) en WGS84 normal. Se guarda el
centroide como punto de referencia + el polígono original en WKT por si
más adelante hace falta un join espacial real (ej. "¿el punto X cae
dentro de una plaza?"), igual que se hizo con comisarías.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests
from shapely import wkt

URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "secretaria-de-desarrollo-urbano/espacios-verdes/espacio_verde_publico.csv"
)

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "espacios_verdes" / "espacios_verdes.csv"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def main() -> None:
    resp = requests.get(URL, timeout=120)
    resp.raise_for_status()
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_PATH.write_bytes(resp.content)

    df = pd.read_csv(RAW_PATH, encoding="utf-8-sig")
    df.columns = [c.strip().lower() for c in df.columns]

    before = len(df)
    df = df.dropna(subset=["geometry"])
    polys = df["geometry"].map(wkt.loads)
    df["lat"] = polys.map(lambda p: p.centroid.y)
    df["lon"] = polys.map(lambda p: p.centroid.x)
    print(f"Espacios verdes: {before} -> {len(df)} tras descartar sin geometría")

    keep_cols = ["id", "nombre", "barrio", "comuna", "clasificac", "area", "lat", "lon", "geometry"]
    df = df[[c for c in keep_cols if c in df.columns]].rename(columns={"geometry": "geometry_wkt"})

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PROCESSED_DIR / "espacios_verdes.parquet", index=False)
    print(f"Guardado: {len(df)} filas")
    print(df["clasificac"].value_counts().head(10))


if __name__ == "__main__":
    main()
