"""
Descarga y normaliza indicadores socioeconómicos por comuna (Instituto de
Vivienda / DGEyC, vía data.buenosaires.gob.ar).

Nivel de ingreso y desempleo NO existen desglosados por comuna en el
portal — solo hay totales a nivel ciudad por año (ver README), inútiles
para diferenciar riesgo entre zonas. NBI (Necesidades Básicas
Insatisfechas) y hacinamiento sí tienen desglose por comuna y son proxies
estándar de vulnerabilidad socioeconómica en la literatura de
criminología argentina — se usan en su lugar.

Ambos datasets ya vienen a nivel de comuna (15 filas cada uno, sin
coordenadas): se cruzan directo con el campo "comuna" que ya existe en
delitos/siniestros/alumbrado, no hace falta geolocalizar nada acá.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

NBI_URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "instituto-de-vivienda/hogares-situacion-vulnerabilidad/NBI-por-comuna.csv"
)
HACINAMIENTO_URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "vivienda-durable-calidad-constructiva/hacinamiento-personas-por-cuarto-por-comuna.csv"
)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "socioeconomico"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


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
    nbi = _download(NBI_URL, "nbi_por_comuna.csv")
    nbi = nbi.rename(columns={"hogares con nbi": "pct_hogares_nbi"})

    hacinamiento = _download(HACINAMIENTO_URL, "hacinamiento_por_comuna.csv")
    hacinamiento = hacinamiento.rename(columns={
        "sin hacinamiento (menos de 2 personas por cuarto)": "pct_sin_hacinamiento",
        "hacinamiento no crítico (2 a 3 personas por cuarto)": "pct_hacinamiento_no_critico",
        "hacinamiento crítico (más de 3 personas por cuarto)": "pct_hacinamiento_critico",
    })

    # ambos datasets traen una fila de total al final ("total"/"total ciudad")
    nbi = nbi[nbi["comuna"].astype(str).str.strip().str.isdigit()]
    hacinamiento = hacinamiento[hacinamiento["comuna"].astype(str).str.strip().str.isdigit()]

    df = nbi.merge(hacinamiento, on="comuna", how="outer")
    df["comuna"] = df["comuna"].astype(int)
    df = df.sort_values("comuna").reset_index(drop=True)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PROCESSED_DIR / "socioeconomico_comuna.parquet", index=False)
    print(f"Guardado: {len(df)} comunas")
    print(df)


if __name__ == "__main__":
    main()
