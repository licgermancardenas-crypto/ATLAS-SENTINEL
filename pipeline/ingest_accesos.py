"""
Descarga y normaliza los peajes y pórticos de autopistas de CABA
(data.buenosaires.gob.ar/dataset/peajes-porticos-autopistas, AUSA) — son
los puntos reales de entrada/salida de la ciudad por autopista.

Dataset chico (11 filas) con dos gotchas de calidad de datos, corregidos
acá: 3 filas no traen id_peaje/descripcion_peaje separados, el nombre
viene pegado al id (ej. "GOP218: Pórtico Salguero") o directamente vacío
con el nombre solo en la descripción; y "autopista" trae espacios/guiones
inconsistentes. Coordenadas ya vienen en WGS84 normal.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ausa/peajes-porticos-autopistas/peajes-y-porticos-autopistas.csv"

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "accesos" / "peajes_porticos.csv"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def main() -> None:
    resp = requests.get(URL, timeout=60)
    resp.raise_for_status()
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_PATH.write_bytes(resp.content)

    df = pd.read_csv(RAW_PATH, encoding="utf-8-sig")
    df.columns = [c.strip().lower() for c in df.columns]

    # id_peaje trae a veces "COD: Nombre" pegado, o queda vacío con el
    # nombre solo en id_peaje (filas de Paseo del Bajo).
    sin_desc = df["descripcion_peaje"].isna()
    df.loc[sin_desc, "descripcion_peaje"] = df.loc[sin_desc, "id_peaje"]
    df["id_peaje"] = df["id_peaje"].str.split(":").str[0].str.strip()
    df["autopista"] = df["autopista"].str.strip().str.replace(r"\s+", " ", regex=True)

    df = df.rename(columns={"long": "lon", "descripcion_peaje": "nombre"})
    df = df[["id_peaje", "nombre", "autopista", "pkm", "lat", "lon"]]

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PROCESSED_DIR / "accesos_autopistas.parquet", index=False)
    print(f"Guardado: {len(df)} peajes/pórticos")
    print(df[["nombre", "autopista"]])


if __name__ == "__main__":
    main()
