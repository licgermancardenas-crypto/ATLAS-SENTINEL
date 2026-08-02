"""
Descarga y normaliza el dataset de Cámaras Fijas de Control Vehicular
(data.buenosaires.gob.ar/dataset/camaras-fijas-control-vehicular).

Dataset chico (225 cámaras). Mismo estilo que alumbrado: separador ";" y
coordenadas con coma decimal.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "transporte-y-obras-publicas/camaras-fijas-control-vehicular/camaras-fijas-de-control-vehicular.csv"
)

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "camaras" / "camaras.csv"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def main() -> None:
    resp = requests.get(URL, timeout=60)
    resp.raise_for_status()
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_PATH.write_bytes(resp.content)

    df = pd.read_csv(RAW_PATH, sep=";", encoding="latin-1", decimal=",")
    df.columns = [c.strip().lower() for c in df.columns]
    df = df.rename(columns={"ubicación": "ubicacion", "ubicaciïn": "ubicacion"})

    before = len(df)
    df = df.dropna(subset=["latitud", "longitud"])
    print(f"Cámaras: {before} -> {len(df)} tras descartar sin geolocalización")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PROCESSED_DIR / "camaras.parquet", index=False)
    print(f"Guardado: {len(df)} filas")
    print(df["tipo_de_fiscalizador"].value_counts())


if __name__ == "__main__":
    main()
