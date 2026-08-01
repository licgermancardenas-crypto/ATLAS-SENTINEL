"""
Descarga y normaliza el feed GTFS de Colectivos
(data.buenosaires.gob.ar/dataset/colectivos-gtfs).

Nota importante: el feed no se actualiza desde 2019-09-30 (el portal lo
marca como "en revisión"). Sirve para geolocalizar paradas y trazados de
recorrido, pero los ramales/frecuencias pueden haber cambiado desde
entonces — no asumir que está al día.

Se procesan stops/routes/trips/shapes. Se descarta stop_times.txt (1.4GB
sin comprimir, horario minuto a minuto por viaje) porque no aporta a un
modelo de riesgo estático por parada; si más adelante hace falta un proxy
de frecuencia/tráfico peatonal por parada, ahí se vuelve a evaluar.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import requests

URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "transporte-y-obras-publicas/colectivos-gtfs/colectivos-gtfs.zip"
)

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "colectivos_gtfs" / "colectivos-gtfs.zip"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

# nombre de archivo dentro del zip -> nombre de salida
FILES_TO_PROCESS = {
    "stops.txt": "colectivos_stops.parquet",
    "routes.txt": "colectivos_routes.parquet",
    "trips.txt": "colectivos_trips.parquet",
    "shapes.txt": "colectivos_shapes.parquet",
}


def download() -> None:
    if RAW_PATH.exists():
        print(f"Ya descargado: {RAW_PATH}")
        return
    resp = requests.get(URL, timeout=300, stream=True)
    resp.raise_for_status()
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RAW_PATH, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            f.write(chunk)


def main() -> None:
    print("Descargando GTFS (209MB)...")
    download()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(RAW_PATH) as zf:
        for member, out_name in FILES_TO_PROCESS.items():
            print(f"Procesando {member}...")
            with zf.open(member) as f:
                df = pd.read_csv(f)
            df.columns = [c.strip().lower() for c in df.columns]
            df.to_parquet(PROCESSED_DIR / out_name, index=False)
            print(f"  {len(df)} filas -> {out_name}")

    stops = pd.read_parquet(PROCESSED_DIR / "colectivos_stops.parquet")
    before = len(stops)
    stops = stops.dropna(subset=["stop_lat", "stop_lon"])
    stops = stops[(stops["stop_lat"] != 0) & (stops["stop_lon"] != 0)]
    stops.to_parquet(PROCESSED_DIR / "colectivos_stops.parquet", index=False)
    print(f"Paradas: {before} -> {len(stops)} tras descartar sin geolocalización")


if __name__ == "__main__":
    main()
