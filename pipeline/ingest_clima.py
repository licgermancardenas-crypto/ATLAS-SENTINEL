"""
Descarga series diarias de temperatura y precipitación para CABA vía la
API pública de NASA POWER (power.larc.nasa.gov) — variable exógena para
el modelo de riesgo (ej. "¿llovió ese día?" afecta caminata/EcoBici).

No se usó el Servicio Meteorológico Nacional (SMN): su único endpoint
público estable (ssl.smn.gob.ar/dpd/zipopendata.php) da nada más que
tiempo actual y pronóstico a 5 días, no histórico; y la página de
descarga de históricos (smn.gob.ar/descarga-de-datos) está detrás de
Cloudflare, no se puede automatizar. NASA POWER no es una estación
puntual sino datos satelitales/de reanálisis (MERRA-2, resolución
~50km) tomados en el punto del Obelisco como referencia de CABA — para
"día lluvioso sí/no" o temperatura de la zona alcanza, no sirve para
diferenciar microclima entre barrios.

Sin autenticación, un solo request cubre todo el rango (probado 2016-01-01
a hoy en un solo call, sin paginar). El valor sentinel -999.0 de la API
marca días sin dato todavía procesado (normalmente los últimos 1-3 días
por la latencia de MERRA-2) — se convierte a NaN.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

# Obelisco, punto de referencia del centro de CABA.
LAT, LON = -34.6037, -58.3816

START = "20160101"
FILL_VALUE = -999.0

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "clima" / "nasa_power_caba.json"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

URL = (
    "https://power.larc.nasa.gov/api/temporal/daily/point"
    f"?parameters=T2M,T2M_MAX,T2M_MIN,PRECTOTCORR&community=RE"
    f"&longitude={LON}&latitude={LAT}&start={START}&end={{end}}&format=JSON"
)


def main() -> None:
    end = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
    resp = requests.get(URL.format(end=end), timeout=120)
    resp.raise_for_status()
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_PATH.write_bytes(resp.content)

    data = resp.json()["properties"]["parameter"]
    df = pd.DataFrame({
        "fecha": pd.to_datetime(list(data["T2M"].keys()), format="%Y%m%d"),
        "temp_media_c": list(data["T2M"].values()),
        "temp_max_c": list(data["T2M_MAX"].values()),
        "temp_min_c": list(data["T2M_MIN"].values()),
        "precipitacion_mm": list(data["PRECTOTCORR"].values()),
    })
    for col in ["temp_media_c", "temp_max_c", "temp_min_c", "precipitacion_mm"]:
        df.loc[df[col] == FILL_VALUE, col] = pd.NA

    df["lluvia"] = df["precipitacion_mm"] > 1.0

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PROCESSED_DIR / "clima_diario.parquet", index=False)
    print(f"Guardado: {len(df)} días, {df['fecha'].min().date()} a {df['fecha'].max().date()}")
    print(f"Días sin dato todavía procesado: {df['temp_media_c'].isna().sum()}")
    print(f"Días con lluvia >1mm: {int(df['lluvia'].sum())} ({df['lluvia'].mean():.1%})")


if __name__ == "__main__":
    main()
