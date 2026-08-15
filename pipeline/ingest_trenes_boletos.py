"""
Pasajeros pagos por estación de tren del AMBA (CNRT), cruzados contra las
estaciones de CABA para poder agregarlos por barrio.

Por qué hace falta: el índice de afluencia no residente del tablero se
construía solo con subte y EcoBici, y al validarlo contra la ENMODO 2018
(`src/validation/validar_presion_visitantes.py`) apareció el punto ciego
esperable — la Comuna 9, Liniers y Mataderos, salía 4ª en la encuesta y 14ª en
el índice, porque ahí se llega en tren y no en subte. Este script trae el modo
que faltaba.

Dos fuentes:

- CNRT, "Boletos vendidos por estación" del AMBA (ZIP con un XLSX por línea,
  1994 al presente, actualización mensual). Los libros traen dashboards y
  tablas dinámicas; los datos limpios están en la hoja "…Bol por Estación", en
  formato largo en las cuatro primeras columnas (AÑO, MES, ESTACIÓN, PAX). El
  resto de las columnas de esa hoja es el mismo dato pivoteado — se ignora.
- BA Data, "Estaciones de Ferrocarril" (GeoJSON). Ojo: pese al nombre, trae
  las 301 estaciones de la red, no solo las de CABA. Las de CABA se reconocen
  porque tienen `barrio` no nulo; las 258 restantes son del conurbano.

El cruce de nombres tiene los mismos problemas que ya tuvo molinetes. Los
casos, todos verificados a mano sobre 43 estaciones —una cantidad donde el
fuzzy match es más riesgo que ayuda—:

- La CNRT usa el nombre oficial largo y BA Data el corto, o al revés:
  "Plaza Constitución" vs "Constitución", "Once" vs "Estación Once".
  Sin los alias se perdían las dos terminales más grandes de la Ciudad,
  37,0M y 15,3M de pasajeros — el 44% del total de CABA.
- Retiro son TRES terminales distintas en el GeoJSON (Mitre, San Martín y
  Belgrano Norte comparten predio y nombre) y TRES entradas distintas en la
  CNRT ("Retiro", "Retiro Ramal Tigre", "Retiro Ramal Suárez/Mitre"). Sin
  tratarlo, cada fila del GeoJSON se llevaba el total de "Retiro" y el barrio
  terminaba con 26,4M en vez de los 15,4M reales: un 71% de más.

Salida: data/processed/trenes_estaciones.parquet — una fila por estación de
CABA con lat/lon y los pasajeros del último año completo. El hex_id se lo pone
después `src/etl/assign_hex_puntual.py`, como al resto de los datasets
puntuales.

Uso: python ingest_trenes_boletos.py
"""

from __future__ import annotations

import json
import unicodedata
import warnings
import zipfile
from pathlib import Path

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parent.parent
RAW = RAIZ / "data" / "raw" / "trenes"
PROCESSED = RAIZ / "data" / "processed"

URL_BOLETOS = ("https://www.argentina.gob.ar/sites/default/files/"
               "ffcc%5Famba%5Fboletosxestacion%5F2026-5%5Fcnrt.zip")
URL_ESTACIONES = ("https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
                  "transporte-y-obras-publicas/estaciones-ferrocarril/"
                  "estaciones_ferroviarias.geojson")

# nombre normalizado en BA Data -> nombre normalizado en la CNRT
ALIAS = {
    "CONSTITUCION": "PLAZA CONSTITUCION",
    "ESTACION ONCE": "ONCE",
    "DR LISANDRO DE LA TORRE": "LISANDRO DE LA TORRE",
    "GENERAL URQUIZA": "GRAL URQUIZA",
    "LUIS MARIA DRAGO": "DR LUIS M DRAGO",
    "LUIS MARIA SAAVEDRA": "SAAVEDRA",
    "PEDRO ARATA": "PEDRO N ARATA",
}

# entradas extra de la CNRT que corresponden a la misma estación física
SUMAR_TAMBIEN = {
    "RETIRO": ["RETIRO RAMAL TIGRE", "RETIRO RAMAL SUAREZ/MITRE"],
}


def norm(s: object) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    for ch in '.-"':
        s = s.replace(ch, " ")
    return " ".join(s.upper().split())


def bajar(url: str, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        print(f"  {destino.name}: ya estaba, no se vuelve a bajar")
        return destino
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    destino.write_bytes(r.content)
    print(f"  {destino.name}: {len(r.content):,} bytes")
    return destino


def leer_boletos(zip_path: Path) -> pd.DataFrame:
    """Formato largo anio/mes/estacion/pax, juntando las 8 líneas."""
    filas = []
    with zipfile.ZipFile(zip_path) as z:
        for miembro in z.namelist():
            if not miembro.lower().endswith(".xlsx"):
                continue
            with z.open(miembro) as fh:
                # los libros traen slicers y tablas dinámicas que openpyxl no
                # soporta; el warning es ruido, los datos se leen igual
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    xl = pd.ExcelFile(fh)
                    hojas = [h for h in xl.sheet_names if "Estaci" in h]
                    if not hojas:
                        continue
                    d = pd.read_excel(xl, sheet_name=hojas[0], header=0, usecols=[0, 1, 2, 3])
            d.columns = ["anio", "mes", "estacion", "pax"]
            d["linea_cnrt"] = Path(miembro).stem.replace("Boletos ", "")
            filas.append(d)
    b = pd.concat(filas, ignore_index=True)
    b["anio"] = pd.to_numeric(b["anio"], errors="coerce")
    b["pax"] = pd.to_numeric(b["pax"], errors="coerce")
    b = b.dropna(subset=["anio", "pax", "estacion"])
    b["k"] = b["estacion"].map(norm)
    return b


def ultimo_anio_completo(b: pd.DataFrame) -> int:
    """El año en curso viene cortado y usarlo subestimaría el volumen."""
    meses = b.groupby("anio")["mes"].nunique()
    completos = meses[meses >= 12].index
    return int(max(completos))


def main() -> None:
    print("Descargando:")
    zip_path = bajar(URL_BOLETOS, RAW / "boletos_x_estacion.zip")
    geo_path = bajar(URL_ESTACIONES, RAW / "estaciones_ferroviarias.geojson")

    b = leer_boletos(zip_path)
    anio = ultimo_anio_completo(b)
    pax = b[b["anio"] == anio].groupby("k")["pax"].sum()
    print(f"\nCNRT: {len(b):,} filas, {int(b.anio.min())}-{int(b.anio.max())}. "
          f"Último año completo: {anio} ({pax.sum():,.0f} pasajeros en toda la red)")

    geo = json.loads(geo_path.read_text(encoding="utf-8"))
    est = pd.DataFrame([{**f["properties"],
                         "lon": f["geometry"]["coordinates"][0],
                         "lat": f["geometry"]["coordinates"][1]}
                        for f in geo["features"]])
    caba = est[est["barrio"].notna()].copy()
    caba["k"] = caba["nombre"].map(norm).replace(ALIAS)

    # Retiro son tres filas del GeoJSON para el mismo predio: si no se
    # deduplica, cada una suma el total de la estación
    dup = caba[caba.duplicated("k", keep=False)]
    if not dup.empty:
        por_barrio = dup.groupby("k")["barrio"].nunique()
        if (por_barrio > 1).any():
            raise SystemExit(
                "Hay estaciones con el mismo nombre en barrios distintos; "
                "deduplicar por nombre las mezclaría:\n"
                f"{dup.loc[dup.k.isin(por_barrio[por_barrio > 1].index)]}")
        print(f"  deduplicadas {len(dup) - dup['k'].nunique()} filas repetidas "
              f"({', '.join(sorted(dup['k'].unique()))})")
    caba = caba.drop_duplicates("k").reset_index(drop=True)

    caba["pax"] = caba["k"].map(pax)
    for base, extras in SUMAR_TAMBIEN.items():
        suma = sum(pax.get(e, 0.0) for e in map(norm, extras))
        if suma:
            caba.loc[caba["k"] == base, "pax"] += suma
            print(f"  {base}: + {suma:,.0f} de {len(extras)} ramales aparte")

    faltan = caba[caba["pax"].isna()]
    if not faltan.empty:
        print(f"\nSIN cruzar ({len(faltan)}): {faltan['nombre'].tolist()}")
        print("  Agregar un alias si alguna es real; no se inventan pasajeros.")
    caba["pax"] = caba["pax"].fillna(0.0)
    caba["anio"] = anio

    cols = ["nombre", "linea", "ramal", "barrio", "comuna", "lat", "lon", "pax", "anio"]
    salida = caba[[c for c in cols if c in caba.columns]]
    PROCESSED.mkdir(parents=True, exist_ok=True)
    salida.to_parquet(PROCESSED / "trenes_estaciones.parquet", index=False)

    print(f"\ntrenes_estaciones.parquet: {len(salida)} estaciones de CABA, "
          f"{salida['pax'].sum():,.0f} pasajeros en {anio} "
          f"({salida['pax'].sum() / pax.sum() * 100:.1f}% de la red)")
    print("\nTop 8 por barrio:")
    print(salida.groupby("barrio")["pax"].sum().nlargest(8)
          .apply(lambda v: f"{v:,.0f}").to_string())


if __name__ == "__main__":
    main()
