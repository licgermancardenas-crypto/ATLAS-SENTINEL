"""
Pasajeros de colectivo por barrio de CABA, cruzando SUBE con el GTFS.

Por qué: el índice de afluencia no residente del tablero venía con subte, tren
y EcoBici, y el colectivo es el modo que más mueve del AMBA — 2.603 millones de
pasajeros en 2025 contra 301M del tren y 194M del subte. Mientras faltó, barrios
como Mataderos quedaban en el percentil 0,02 pese a recibir gente todos los días.

El problema de fondo: **SUBE informa por línea, no por parada.** No existe
publicado dónde sube cada pasajero. Así que hay que repartir los boletos de cada
línea entre sus paradas, y eso es un supuesto, no un dato:

    pax_barrio = Σ_línea  pax_línea × (paradas de la línea en el barrio
                                       / paradas totales de la línea)

O sea, se asume que las subidas se reparten **parejo a lo largo del recorrido**.
Es falso —las cabeceras y los nodos de trasbordo concentran mucho más— pero es
el supuesto neutral: cualquier alternativa exige inventar dónde está la demanda.
Dividir por las paradas TOTALES y no solo por las de CABA es lo que hace que una
línea que apenas entra a la Ciudad aporte poco, en vez de volcarle todo el
recorrido del conurbano.

Dos límites más, que hay que tener presentes al leer el resultado:

- El GTFS de colectivos es el feed de 2020-02-10, el único publicado. Los
  recorridos son bastante estables, pero no es dato fresco.
- Cruzan 267 de las 323 líneas del AMBA, el 85,7% de los pasajeros. Las que
  quedan afuera son sobre todo de la serie 500, suburbanas, que en su mayoría
  no entran a CABA — el faltante pesa menos de lo que sugiere el conteo.

Entradas:
  data/raw/sube/usos-2025.csv        de datos.transporte.gob.ar (SUBE, usos por
                                     fecha; se filtra COLECTIVO + AMBA)
  data/raw/colectivos_gtfs/colectivos-gtfs.zip   ya lo baja ingest_colectivos_gtfs.py

Salida: data/features/colectivos_barrio.parquet — barrio, pax, paradas.
Se agrega directo por barrio y no por parada porque el reparto es uniforme:
guardar una fila por parada daría una precisión que el método no tiene.

Uso: python ingest_colectivos_sube.py
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
RAW = RAIZ / "data" / "raw"
FEATURES = RAIZ / "data" / "features"
GTFS = RAW / "colectivos_gtfs" / "colectivos-gtfs.zip"
SUBE = RAW / "sube" / "usos-2025.csv"

FILAS_POR_CHUNK = 1_000_000


def num_linea(s: object) -> int | None:
    """El número de línea, sacando los prefijos que SUBE usa sin criterio fijo
    (BSAS_LINEA_002, BS_ASLINEA_123, BS_AS_LINEA 715M) y el ramal del GTFS
    (505R3 -> 505)."""
    t = str(s).upper()
    for basura in ("BS_AS", "BSAS", "BS AS", "LINEA"):
        t = t.replace(basura, "")
    m = re.search(r"(\d+)", t)
    return int(m.group(1)) if m else None


def pax_por_linea() -> pd.Series:
    d = pd.read_csv(SUBE, low_memory=False,
                    usecols=["LINEA", "AMBA", "TIPO_TRANSPORTE", "CANTIDAD"])
    d = d[(d["TIPO_TRANSPORTE"] == "COLECTIVO") & (d["AMBA"] == "SI")]
    d["n"] = [num_linea(x) for x in d["LINEA"]]
    s = d.dropna(subset=["n"]).groupby("n")["CANTIDAD"].sum()
    print(f"SUBE: {len(s)} líneas del AMBA, {s.sum():,.0f} pasajeros en 2025")
    return s


def paradas_por_linea() -> pd.DataFrame:
    """(n_linea, stop_id) únicos. stop_times son 1,4GB, así que se lee en
    chunks de dos columnas y se acumula un set — nunca entra entero en RAM."""
    with zipfile.ZipFile(GTFS) as z:
        trips = pd.read_csv(z.open("trips.txt"), usecols=["trip_id", "route_id"],
                            dtype=str)
        routes = pd.read_csv(z.open("routes.txt"),
                             usecols=["route_id", "route_short_name"], dtype=str)
        routes["n"] = [num_linea(x) for x in routes["route_short_name"]]
        trip_a_linea = (trips.merge(routes[["route_id", "n"]], on="route_id", how="left")
                        .dropna(subset=["n"]).set_index("trip_id")["n"].to_dict())
        print(f"GTFS: {len(routes)} recorridos, {routes['n'].nunique()} líneas, "
              f"{len(trip_a_linea):,} viajes")

        pares: set[tuple[int, str]] = set()
        leidas = 0
        with z.open("stop_times.txt") as fh:
            for chunk in pd.read_csv(fh, usecols=["trip_id", "stop_id"], dtype=str,
                                     chunksize=FILAS_POR_CHUNK):
                chunk["n"] = chunk["trip_id"].map(trip_a_linea)
                chunk = chunk.dropna(subset=["n"])
                pares.update(zip(chunk["n"].astype(int), chunk["stop_id"]))
                leidas += len(chunk)
                print(f"  stop_times: {leidas:,} filas, {len(pares):,} pares únicos",
                      end="\r", flush=True)
    print()
    return pd.DataFrame(sorted(pares), columns=["n", "stop_id"])


def main() -> None:
    for ruta in (GTFS, SUBE):
        if not ruta.exists():
            sys.exit(f"Falta {ruta} — ver el docstring.")

    pax = pax_por_linea()
    pares = paradas_por_linea()

    # barrio de cada parada, por el mismo camino que el resto del pipeline
    stops = pd.read_parquet(RAIZ / "data/processed/colectivos_stops.parquet")
    sys.path.insert(0, str(RAIZ / "src" / "etl"))
    from hex_utils import asignar_hex_id  # noqa: E402

    stops["hex_id"] = asignar_hex_id(stops, "stop_lat", "stop_lon")
    hexes = (pd.read_parquet(FEATURES / "hex_maestra.parquet")
             .dropna(subset=["barrio_id"])[["hex_id", "barrio_id"]])
    hexes["hex_id"] = hexes["hex_id"].astype(str)
    stops["hex_id"] = stops["hex_id"].astype(str)
    stops = stops.merge(hexes, on="hex_id", how="left")
    en_caba = stops["barrio_id"].notna().sum()
    print(f"paradas: {len(stops):,} en el feed, {en_caba:,} dentro de CABA")

    pares["stop_id"] = pares["stop_id"].astype(str)
    stops["stop_id"] = stops["stop_id"].astype(str)
    pares = pares.merge(stops[["stop_id", "barrio_id"]], on="stop_id", how="left")

    totales = pares.groupby("n")["stop_id"].nunique()
    en_barrio = (pares.dropna(subset=["barrio_id"])
                 .groupby(["n", "barrio_id"])["stop_id"].nunique())

    cruzan = totales.index.intersection(pax.index)
    print(f"cruzan {len(cruzan)} líneas · {pax.loc[cruzan].sum() / pax.sum() * 100:.1f}% "
          f"de los pasajeros del AMBA")

    df = en_barrio.rename("paradas").reset_index()
    df = df[df["n"].isin(cruzan)]
    df["pax"] = (df["n"].map(pax) * df["paradas"] / df["n"].map(totales))

    salida = (df.groupby("barrio_id")
              .agg(pax=("pax", "sum"), paradas=("paradas", "sum"))
              .reset_index().rename(columns={"barrio_id": "barrio"}))
    FEATURES.mkdir(parents=True, exist_ok=True)
    salida.to_parquet(FEATURES / "colectivos_barrio.parquet", index=False)

    print(f"\ncolectivos_barrio.parquet: {len(salida)} barrios, "
          f"{salida['pax'].sum():,.0f} pasajeros asignados a CABA "
          f"({salida['pax'].sum() / pax.loc[cruzan].sum() * 100:.1f}% de las líneas que cruzan)")
    print("\nTop 8:")
    print(salida.nlargest(8, "pax")[["barrio", "pax", "paradas"]]
          .assign(pax=lambda d: d["pax"].map("{:,.0f}".format)).to_string(index=False))


if __name__ == "__main__":
    main()
