"""
Descarga y normaliza los polígonos oficiales de los 48 barrios de CABA
(data.buenosaires.gob.ar/dataset/barrios).

A diferencia de espacios_verdes/comisarias, acá el WKT viene en WGS84
normal (grados) — no hace falta reproyectar. Cada barrio ya trae su
comuna asignada, así que sirve como unidad intermedia entre comuna (15,
demasiado grande) y radio censal (3.554, quizás demasiado chico para
mostrar en UI) para agrupar/visualizar riesgo.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests
from shapely import wkt

URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/innovacion-transformacion-digital/barrios/barrios.csv"

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "barrios" / "barrios.csv"
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
    polys = df["geometry"].map(wkt.loads)
    df["lat"] = polys.map(lambda p: p.centroid.y)
    df["lon"] = polys.map(lambda p: p.centroid.x)
    print(f"Barrios: {before} -> {len(df)} tras descartar sin geometría")

    df = df.rename(columns={
        "geometry": "geometry_wkt",
        "area_metro": "area_m2",
        "perimetro_": "perimetro_m",
    })[["id", "nombre", "comuna", "area_m2", "perimetro_m", "lat", "lon", "geometry_wkt"]]

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PROCESSED_DIR / "barrios.parquet", index=False)
    print(f"Guardado: {len(df)} barrios en {df['comuna'].nunique()} comunas")


if __name__ == "__main__":
    main()
