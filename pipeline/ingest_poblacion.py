"""
Descarga y normaliza población total por comuna y por barrio
(data.buenosaires.gob.ar/dataset/estructura-demografica y /barrios).

Dos tablas chicas sin geometría (se cruzan por nombre/código contra
barrios.parquet y radios_censales.parquet):

- Población por comuna: estimación 2017 (DGEyC), complementa
  socioeconomico_comuna.parquet, que tiene NBI/hacinamiento pero no
  población total.
- Población por barrio: censo 2010, mismo año que radios_censales.parquet
  (de hecho es redundante con la suma de radios por barrio — se guarda
  igual por ser la fuente directa y más simple de usar en la UI).

Gotcha de nombres: el dataset de población usa "BOCA", el de barrios.csv
usa "LA BOCA" — único mismatch entre los 48 nombres, se corrige a mano
acá (ver ALIAS).

Se buscó desglose de población por edad/sexo a nivel comuna o barrio y
NO existe en este portal: "Estructura poblacional según grandes grupos
de edad" (est_pob_sexo__annio__g_edad_limpio.csv) es solo a nivel ciudad
completa, serie histórica 1855-presente en porcentajes, sin ningún campo
espacial — no sirve para diferenciar riesgo entre zonas y no se ingesta.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

URL_COMUNA = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/comunas/gcba_pob_comunas_17.csv"
URL_BARRIO = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/barrios/caba_pob_barrios_2010.csv"

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "poblacion"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

ALIAS_BARRIO = {"BOCA": "LA BOCA"}


def _download(url: str, name: str) -> pd.DataFrame:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / name
    path.write_bytes(resp.content)
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def main() -> None:
    comuna = _download(URL_COMUNA, "poblacion_comuna_2017.csv")
    comuna["comuna"] = comuna["comuna"].astype(int)
    comuna = comuna.sort_values("comuna").reset_index(drop=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    comuna.to_parquet(PROCESSED_DIR / "poblacion_comuna.parquet", index=False)
    print(f"Población por comuna: {len(comuna)} filas, total {comuna['poblacion'].sum():,}")

    barrio = _download(URL_BARRIO, "poblacion_barrio_2010.csv")
    barrio["barrio"] = barrio["barrio"].str.strip().str.upper().replace(ALIAS_BARRIO)
    barrio = barrio.sort_values("barrio").reset_index(drop=True)
    barrio.to_parquet(PROCESSED_DIR / "poblacion_barrio.parquet", index=False)
    print(f"Población por barrio: {len(barrio)} filas, total {barrio['poblacion'].sum():,}")


if __name__ == "__main__":
    main()
