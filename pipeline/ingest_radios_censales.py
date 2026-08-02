"""
Descarga y normaliza los radios censales de CABA con datos del Censo 2010
(data.buenosaires.gob.ar/dataset/informacion-censal-por-radio).

Es la unidad de análisis más chica disponible con población real (3.554
radios, ~800 habitantes cada uno en promedio) — el denominador que faltaba
para pasar de "cantidad de delitos" a "delitos per cápita" y para pesar el
"último tramo a pie" del modelo de riesgo a una escala más fina que comuna
(15) o barrio (48).

Trae además NBI por radio (H_CON_NBI / T_HOGAR), mucho más granular que
socioeconomico_comuna.parquet — se mantienen ambos: el de comuna sigue
sirviendo para cruzar con delitos/siniestros que solo traen comuna, este
para análisis espacial fino.

Solo existe a nivel radio para 2001 y 2010 en este portal — no se
encontró censo 2022 desglosado por radio publicado acá (el portal
geoestadístico de INDEC podría tenerlo pero con otra cartografía/códigos;
no se cruzó). 2010 es el más reciente disponible con esta granularidad.

El WKT viene en WGS84 normal, igual que barrios — no hace falta
reproyectar.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests
from shapely import wkt

URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "direccion-general-de-estadisticas-y-censos/informacion-censal-por-radio/"
    "informacion-censal-por-radio-2010.csv"
)

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "radios_censales" / "radios_censales_2010.csv"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

COLUMN_MAP = {
    "wkt": "geometry_wkt",
    "id": "id_radio",
    "co_frac_ra": "cod_frac_radio",
    "comuna": "comuna",
    "fraccion": "fraccion",
    "radio": "radio",
    "total_pob": "poblacion_total",
    "t_varon": "poblacion_varones",
    "t_mujer": "poblacion_mujeres",
    "t_vivienda": "viviendas_total",
    "v_particul": "viviendas_particulares",
    "v_colectiv": "viviendas_colectivas",
    "t_hogar": "hogares_total",
    "h_con_nbi": "hogares_con_nbi",
    "h_sin_nbi": "hogares_sin_nbi",
}


def main() -> None:
    resp = requests.get(URL, timeout=60)
    resp.raise_for_status()
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_PATH.write_bytes(resp.content)

    df = pd.read_csv(RAW_PATH, encoding="utf-8-sig")
    df.columns = [c.strip().lower() for c in df.columns]
    df = df.rename(columns=COLUMN_MAP)

    before = len(df)
    df = df.dropna(subset=["geometry_wkt"])
    polys = df["geometry_wkt"].map(wkt.loads)
    df["lat"] = polys.map(lambda p: p.centroid.y)
    df["lon"] = polys.map(lambda p: p.centroid.x)
    print(f"Radios censales: {before} -> {len(df)} tras descartar sin geometría")

    df["pct_hogares_nbi"] = (df["hogares_con_nbi"] / df["hogares_total"]).fillna(0)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PROCESSED_DIR / "radios_censales.parquet", index=False)
    print(f"Guardado: {len(df)} radios, población total {df['poblacion_total'].sum():,}")
    print(f"Comunas cubiertas: {sorted(df['comuna'].unique())}")


if __name__ == "__main__":
    main()
