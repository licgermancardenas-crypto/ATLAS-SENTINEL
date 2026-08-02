"""
Descarga y normaliza los permisos de eventos masivos de CABA
(data.buenosaires.gob.ar/dataset/permisos-eventos-masivos, Agencia
Gubernamental de Control) — variable exógena para el modelo de riesgo:
recitales, festivales, eventos deportivos y manifestaciones concentran
gente (y afectan el patrón de "último tramo a pie") en fechas puntuales.

Solo hay archivos publicados para 2019, 2023, 2024, 2025 y 2026 — 2020,
2021 y 2022 no están en el portal (no se investigó por qué; no asumir que
significa "sin eventos" esos años, simplemente no están publicados).

El esquema cambia de archivo a archivo, sin documentarlo — tres formatos
distintos conviven:
- 2019: separado por comas, trae lat/lon reales y "capacidad"/"fecha" en
  texto libre (a veces varias fechas o "todo el mes" en un solo campo).
- 2023: separado por ";", solo 19 filas y todas de febrero 2023 (archivo
  claramente parcial) — sin barrio, sin aforo, sin geolocalización, fecha
  como día suelto que hay que combinar con "periodo" (aaaamm). Además es
  el único de los 5 archivos en cp850 (DOS Latin US) en vez de utf-8 — se
  detectó porque "Denominación" rompía el parser.
- 2024/2025/2026: separado por ";", con aforo y barrio pero sin lat/lon.

Por la heterogeneidad, "fecha" y "aforo" son best-effort: se parsean solo
cuando el formato es inequívoco, si no quedan en null y el texto original
se conserva en fecha_raw/aforo_raw. lat/lon solo están pobladas para las
filas que vienen del archivo 2019; para el resto habría que geocodificar
"lugar" a mano o cruzar contra estadios.parquet / barrios.parquet.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import requests

BASE = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/agencia-gubernamental-de-control/permisos-eventos-masivos/"
URLS = {
    2019: BASE + "permisos-eventos-masivos.csv",
    2023: BASE + "permisos-eventos-masivos-2023.csv",
    2024: BASE + "permisos-eventos-masivos-2024.csv",
    2025: BASE + "permisos-eventos-masivos-2025.csv",
    2026: BASE + "permisos-eventos-masivos-2026.csv",
}

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "eventos_masivos"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def _download(year: int) -> Path:
    resp = requests.get(URLS[year], timeout=60)
    resp.raise_for_status()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"eventos_masivos_{year}.csv"
    path.write_bytes(resp.content)
    return path


def _parse_aforo(raw) -> float | None:
    if pd.isna(raw):
        return None
    m = re.search(r"[\d.]+", str(raw))
    if not m:
        return None
    digits = m.group().replace(".", "")
    return float(digits) if digits else None


def _parse_fecha_unica(raw) -> pd.Timestamp | None:
    if pd.isna(raw):
        return None
    matches = DATE_RE.findall(str(raw))
    if len(matches) != 1:
        return None
    d, m, y = matches[0]
    try:
        return pd.Timestamp(year=int(y), month=int(m), day=int(d))
    except ValueError:
        return None


def _normalizar_2019(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = [c.strip().lower() for c in df.columns]
    return pd.DataFrame({
        "fecha": df["fecha"].map(_parse_fecha_unica),
        "fecha_raw": df["fecha"],
        "evento": df["denominacion_evento"],
        "lugar": df["predio"],
        "barrio": df["barrio"].str.strip().str.upper(),
        "aforo": df["capacidad"].map(_parse_aforo),
        "aforo_raw": df["capacidad"],
        "lat": df["lat"],
        "lon": df["long"],
        "anio_archivo": 2019,
    })


def _normalizar_2023(path: Path) -> pd.DataFrame:
    # Único de los 5 archivos que no viene en utf-8: es cp850 (DOS Latin US) —
    # se descubrió porque "Denominación" rompía el parser en utf-8/latin-1.
    df = pd.read_csv(path, sep=";", encoding="cp850")
    df.columns = [c.strip().lower() for c in df.columns]

    def fecha_desde_periodo(row) -> pd.Timestamp | None:
        dia_raw = str(row["fecha de realizacion del evento"]).strip()
        if not dia_raw.isdigit():
            return None
        periodo = str(row["periodo"])
        try:
            return pd.Timestamp(year=int(periodo[:4]), month=int(periodo[4:6]), day=int(dia_raw))
        except ValueError:
            return None

    return pd.DataFrame({
        "fecha": df.apply(fecha_desde_periodo, axis=1),
        "fecha_raw": df["periodo"].astype(str) + " / día " + df["fecha de realizacion del evento"].astype(str),
        "evento": df["denominación del evento"],
        "lugar": df["predio"],
        "barrio": None,
        "aforo": None,
        "aforo_raw": None,
        "lat": None,
        "lon": None,
        "anio_archivo": 2023,
    })


def _normalizar_formato_nuevo(path: Path, anio: int) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", encoding="utf-8-sig")
    df.columns = [c.strip().lower() for c in df.columns]
    return pd.DataFrame({
        "fecha": pd.to_datetime(df["fecha"], dayfirst=True, errors="coerce"),
        "fecha_raw": df["fecha"],
        "evento": df["evento"],
        "lugar": df["lugar"],
        "barrio": df["barrio"].str.strip().str.upper(),
        "aforo": df["aforo"].map(_parse_aforo),
        "aforo_raw": df["aforo"],
        "lat": None,
        "lon": None,
        "anio_archivo": anio,
    })


def main() -> None:
    paths = {year: _download(year) for year in URLS}

    partes = [
        _normalizar_2019(paths[2019]),
        _normalizar_2023(paths[2023]),
        _normalizar_formato_nuevo(paths[2024], 2024),
        _normalizar_formato_nuevo(paths[2025], 2025),
        _normalizar_formato_nuevo(paths[2026], 2026),
    ]
    df = pd.concat(partes, ignore_index=True)
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["aforo_raw"] = df["aforo_raw"].map(lambda x: None if pd.isna(x) else str(x))
    df["fecha_raw"] = df["fecha_raw"].map(lambda x: None if pd.isna(x) else str(x))

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PROCESSED_DIR / "eventos_masivos.parquet", index=False)

    print(f"Guardado: {len(df)} eventos")
    print(df.groupby("anio_archivo").agg(
        filas=("evento", "size"),
        con_fecha=("fecha", lambda s: s.notna().sum()),
        con_barrio=("barrio", lambda s: s.notna().sum()),
        con_aforo=("aforo", lambda s: s.notna().sum()),
        con_geo=("lat", lambda s: s.notna().sum()),
    ))


if __name__ == "__main__":
    main()
