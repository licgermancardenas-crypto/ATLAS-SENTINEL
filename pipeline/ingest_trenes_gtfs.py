"""
Descarga y normaliza el feed GTFS de Trenes (trenes de media/larga
distancia: Sarmiento, Mitre, Roca, etc.) — data.buenosaires.gob.ar/dataset/trenes-gtfs.

Extiende la cobertura geográfica más allá de CABA hacia el conurbano, a
diferencia de todo lo demás ingerido hasta ahora. Nota: el feed es de
2020-02-10, sin actualizaciones desde entonces — mismo caveat que
colectivos GTFS.

A diferencia de colectivos, acá sí se procesa stop_times.txt (2.7MB,
nada comparado a los 1.4GB de colectivos) porque el feed completo es
chico.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import requests

URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/trenes-gtfs/trenes-gtfs.zip"

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "trenes_gtfs" / "trenes-gtfs.zip"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

FILES_TO_PROCESS = {
    "stops.txt": "trenes_stops.parquet",
    "routes.txt": "trenes_routes.parquet",
    "trips.txt": "trenes_trips.parquet",
    "shapes.txt": "trenes_shapes.parquet",
    "stop_times.txt": "trenes_stop_times.parquet",
}


def main() -> None:
    resp = requests.get(URL, timeout=60)
    resp.raise_for_status()
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_PATH.write_bytes(resp.content)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(RAW_PATH) as zf:
        for member, out_name in FILES_TO_PROCESS.items():
            with zf.open(member) as f:
                df = pd.read_csv(f)
            df.columns = [c.strip().lower() for c in df.columns]
            df.to_parquet(PROCESSED_DIR / out_name, index=False)
            print(f"{member}: {len(df)} filas -> {out_name}")

    stops = pd.read_parquet(PROCESSED_DIR / "trenes_stops.parquet")
    before = len(stops)
    stops = stops.dropna(subset=["stop_lat", "stop_lon"])
    stops.to_parquet(PROCESSED_DIR / "trenes_stops.parquet", index=False)
    print(f"Paradas: {before} -> {len(stops)} tras descartar sin geolocalización")


if __name__ == "__main__":
    main()
