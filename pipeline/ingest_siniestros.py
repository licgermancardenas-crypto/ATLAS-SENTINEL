"""
Descarga y normaliza el dataset de Siniestros Viales CABA
(data.buenosaires.gob.ar/dataset/victimas-siniestros-viales).

A diferencia de delitos, este dataset no está partido por año: son dos
archivos únicos que cubren 2019-2025.

- hechos: un registro por siniestro, con geolocalización y gravedad.
- victimas: un registro por víctima (sin geolocalización propia; se
  vincula a "hechos" por id_siniestro si hace falta cruzar demografía).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

BASE_URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "transporte-y-obras-publicas/victimas-siniestros-viales/{name}.csv"
)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "siniestros"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

# El CSV viene con BOM, separado por ";" (a diferencia de delitos, que usa ",")
# y usa el string "SD" ("sin dato") como nulo en vez de dejar la celda vacía.
READ_KWARGS = dict(sep=";", encoding="utf-8-sig", na_values=["SD"], low_memory=False)


def download(name: str) -> pd.DataFrame:
    url = BASE_URL.format(name=name)
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    raw_path = RAW_DIR / f"{name}.csv"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(resp.content)

    df = pd.read_csv(raw_path, **READ_KWARGS)
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def main() -> None:
    print("Descargando hechos...")
    hechos = download("siniestros_viales_hechos")

    before = len(hechos)
    hechos = hechos.dropna(subset=["latitud_siniestro", "longitud_siniestro"])
    hechos = hechos[(hechos["latitud_siniestro"] != 0) & (hechos["longitud_siniestro"] != 0)]
    print(f"Hechos: {before} -> {len(hechos)} tras descartar sin geolocalización")

    hechos["fecha_siniestro"] = pd.to_datetime(hechos["fecha_siniestro"], errors="coerce")

    print("Descargando víctimas...")
    victimas = download("siniestros_viales_victimas")
    victimas["fecha_siniestro"] = pd.to_datetime(victimas["fecha_siniestro"], errors="coerce")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    hechos.to_parquet(PROCESSED_DIR / "siniestros_hechos.parquet", index=False)
    victimas.to_parquet(PROCESSED_DIR / "siniestros_victimas.parquet", index=False)
    print(f"Guardado: {len(hechos)} hechos, {len(victimas)} víctimas")

    print(hechos["gravedad_siniestro"].value_counts())
    print(hechos["anio_siniestro"].value_counts().sort_index())


if __name__ == "__main__":
    main()
