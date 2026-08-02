"""
Descarga y normaliza el callejero de CABA (data.buenosaires.gob.ar/dataset/calles) —
la red vial completa con jerarquización de cada tramo, necesaria para pesar
el riesgo por tipo de vía (troncal/distribuidora/local) y para el "último
tramo a pie" del modelo.

Gotcha de nombres de columna: el dataset tiene una columna "long" que NO es
longitud geográfica, es el LARGO del tramo de calle en metros — se renombra
a "largo_m" para evitar confundirla con la coordenada. La geometría es un
LINESTRING (un tramo de calle, no un punto) en WGS84 normal, no hace falta
reproyectar; se guarda el WKT completo más un punto representativo
(centroide del tramo) para joins simples tipo "qué tan cerca está esto de
una calle troncal".

1.729 de 31.961 tramos no tienen comuna asignada (autopistas/bordes que
cruzan el límite de una sola comuna) — se mantienen igual, no se descartan.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests
from shapely import wkt

URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/jefatura-de-gabinete-de-ministros/calles/callejero.csv"

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "calles" / "callejero.csv"
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
    lines = df["geometry"].map(wkt.loads)
    df["lat"] = lines.map(lambda g: g.centroid.y)
    df["lon"] = lines.map(lambda g: g.centroid.x)
    print(f"Calles: {before} -> {len(df)} tras descartar sin geometría")
    print(f"Sin comuna asignada: {df['comuna'].isna().sum()}")

    df = df.rename(columns={
        "long": "largo_m",
        "nomoficial": "nombre",
        "tipo_c": "tipo_via",
        "red_jerarq": "jerarquia",
        "geometry": "geometry_wkt",
    })[[
        "id", "codigo", "nombre", "tipo_via", "jerarquia", "sentido", "largo_m",
        "bicisenda", "comuna", "barrio", "lat", "lon", "geometry_wkt",
    ]]

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PROCESSED_DIR / "calles.parquet", index=False)
    print(f"Guardado: {len(df)} tramos de calle")
    print(df["jerarquia"].value_counts())


if __name__ == "__main__":
    main()
