"""
Descarga y normaliza el dataset de Divisiones de Comisarías Vecinales
(data.buenosaires.gob.ar/dataset/divisiones-comisarias-vecinales).

Importante: esto NO es la ubicación puntual de cada comisaría, son los
polígonos de zona de patrullaje de cada división vecinal (en lat/lon
WGS84 normal, a diferencia de escuelas/hospitales). Se guarda el
centroide como aproximación de "dónde está el centro de la zona", más el
polígono original en WKT por si más adelante hace falta un join espacial
punto-en-polígono real en vez de solo distancia al centroide.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests
from shapely import wkt

URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "ministerio-de-justicia-y-seguridad/divisiones-comisarias-vecinales/division_comisaria_vecinal.csv"
)

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "comisarias" / "comisarias.csv"
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
    print(f"Divisiones: {before} -> {len(df)} tras descartar sin geometría")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.rename(columns={"geometry": "geometry_wkt"}).to_parquet(PROCESSED_DIR / "comisarias.parquet", index=False)
    print(f"Guardado: {len(df)} filas")


if __name__ == "__main__":
    main()
