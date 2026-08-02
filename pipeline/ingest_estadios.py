"""
Descarga y normaliza el listado de estadios de CABA
(data.buenosaires.gob.ar/dataset/estadios) — útil para modelar el efecto
"día de evento" cerca de cada estadio, cruzando con permisos_eventos_masivos.

Igual que escuelas/hospitales, el WKT POINT viene en el sistema plano
legacy ("0 de Flores"), no en el nuevo GKBA 2019 — se reproyecta con
geo_utils.gkba_legacy_point_to_latlon (verificado: el sistema nuevo tira
los puntos ~30km fuera de CABA, el legacy los deja en rango correcto).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from geo_utils import gkba_legacy_point_to_latlon

URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/vicejefatura-de-gobierno/estadios/estadios.csv"

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "estadios" / "estadios.csv"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def main() -> None:
    resp = requests.get(URL, timeout=60)
    resp.raise_for_status()
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_PATH.write_bytes(resp.content)

    df = pd.read_csv(RAW_PATH, sep=";", encoding="utf-8-sig")
    df.columns = [c.strip().lower() for c in df.columns]

    before = len(df)
    df = df.dropna(subset=["geometry"])
    df["lat"], df["lon"] = gkba_legacy_point_to_latlon(df["geometry"])
    print(f"Estadios: {before} -> {len(df)} tras descartar sin geolocalización")

    df = df.rename(columns={
        "fna": "nombre_completo",
        "gna": "tipo",
        "nam": "nombre",
        "aso": "institucion",
        "dir": "direccion",
        "bar": "barrio",
        "com": "comuna",
    })[["id", "nombre", "nombre_completo", "tipo", "institucion", "direccion", "barrio", "comuna", "web", "lat", "lon"]]

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PROCESSED_DIR / "estadios.parquet", index=False)
    print(f"Guardado: {len(df)} estadios")


if __name__ == "__main__":
    main()
