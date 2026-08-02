"""
Descarga y agrega los recorridos de EcoBici (bicicletas-publicas), 2010-2026.

Dos cosas obligan a un diseño distinto al de los datasets chicos:

1. La máquina donde corre esto tiene 3.4GB de RAM total. El CSV de 2019
   sólo (el año de mayor volumen) pesa 1.9GB descomprimido — cargarlo
   entero en pandas lo colgaría. Todo se lee en chunks (streaming),
   nunca se materializa un año completo en memoria.

2. El esquema 2019+ tiene filas con datos corridos: la coordenada de la
   estación destino a veces viene pegada en un solo campo en vez de dos
   (ej. "-34.58,-58.42" dentro de lat_estacion_destino), o directamente
   swapeada. No se puede confiar en la coordenada por viaje. Por eso se
   arma una tabla canónica de estaciones (mediana de lat/lon por
   id_estacion sobre todas las observaciones válidas del histórico) en
   vez de tomar la coordenada de cada fila al pie de la letra.

Con esas dos restricciones, no tiene sentido guardar cada viaje
individual (serían ~8.8GB que ni la RAM ni el caso de uso justifican).
Se agrega directo a "viajes por estación / hora / día de semana", que es
lo que el modelo de riesgo necesita como proxy de tráfico peatonal.

Limitación conocida: 2014 usa un esquema propio, único en todo el
histórico (columnas ID,NOMBRE_ORIGEN,ORIGEN_FECHA,DESTINO_ESTACION,
DESTINO_FECHA — nombre de estación en vez de id_estacion, sin
coordenadas). No matchea con RENAME_MAP/KEEP_COLUMNS, así que sus
~1M viajes (~2% del total) quedan fuera del agregado. Se podría
recuperar cruzando NOMBRE_ORIGEN/DESTINO_ESTACION contra
nombre_estacion de la tabla canónica, pero no vale el esfuerzo dado
el volumen: se documenta como gap conocido en vez de resolverlo.
"""

from __future__ import annotations

import zipfile
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import requests

BASE = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "transporte-y-obras-publicas/bicicletas-publicas/recorridos-realizados-{year}.{ext}"
)

YEARS_CSV = {2010, 2011, 2012, 2013}  # únicos años publicados sin comprimir
YEARS = list(range(2010, 2027))

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "ecobici"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

CHUNKSIZE = 100_000

# Buenos Aires, bounding box generoso — descarta coordenadas corridas/basura
LAT_MIN, LAT_MAX = -34.75, -34.50
LON_MIN, LON_MAX = -58.60, -58.30

RENAME_MAP = {
    "id_recorrido": "trip_id",
    "fecha_origen_recorrido": "fecha_origen",
    "long_estacion_origen": "lon_origen",
    "lat_estacion_origen": "lat_origen",
    "fecha_destino_recorrido": "fecha_destino",
    "long_estacion_destino": "lon_destino",
    "lat_estacion_destino": "lat_destino",
}

KEEP_COLUMNS = [
    "fecha_origen", "id_estacion_origen", "nombre_estacion_origen", "lat_origen", "lon_origen",
    "fecha_destino", "id_estacion_destino", "nombre_estacion_destino", "lat_destino", "lon_destino",
]


def _raw_path(year: int) -> Path:
    ext = "csv" if year in YEARS_CSV else "zip"
    return RAW_DIR / f"recorridos-{year}.{ext}"


def _is_valid_cached_file(path: Path) -> bool:
    # Una corrida anterior se cortó a mitad de una descarga (taskkill) y
    # dejó un .zip truncado en disco con tamaño "razonable" pero sin
    # central directory. Sin esta validación, _ensure_downloaded confiaría
    # en el archivo para siempre porque nunca vuelve a chequear su
    # integridad, solo si existe.
    if path.suffix != ".zip":
        return True
    try:
        with zipfile.ZipFile(path) as zf:
            return zf.testzip() is None
    except zipfile.BadZipFile:
        return False


def _ensure_downloaded(year: int) -> Path:
    path = _raw_path(year)
    if path.exists():
        if _is_valid_cached_file(path):
            return path
        print(f"  {path.name} está corrupto (descarga anterior incompleta), re-descargando...")
        path.unlink()

    url = BASE.format(year=year, ext=path.suffix.lstrip("."))
    print(f"  descargando {url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, timeout=300, stream=True) as resp:
        resp.raise_for_status()
        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    return path


@contextmanager
def _open_csv_stream(year: int):
    # zipfile.ZipFile no se cierra solo con cerrar el stream que devuelve
    # zf.open(...) — hacía falta este context manager para liberar el
    # handle del .zip en sí. Sin esto, después de ~6-8 años procesados en
    # el mismo proceso se acumulan handles sin cerrar y Windows empieza a
    # fallar aperturas nuevas con "BadZipFile: File is not a zip file"
    # (el síntoma no tiene nada que ver con que el archivo esté corrupto).
    path = _ensure_downloaded(year)
    if path.suffix == ".csv":
        f = open(path, "rb")
        try:
            yield f
        finally:
            f.close()
        return

    zf = zipfile.ZipFile(path)
    try:
        stream = zf.open(zf.namelist()[0])
        try:
            yield stream
        finally:
            stream.close()
    finally:
        zf.close()


def _normalize_station_id(series: pd.Series) -> pd.Series:
    # El esquema 2019+ sufija el id con "BAEcobici" (ej. "17BAEcobici").
    # Es el mismo número de estación que usa el esquema viejo (ej. 17 =
    # "017 - Plaza Almagro" en ambos) — se extrae el número para unificar
    # el namespace de estaciones entre épocas en vez de dejarlas separadas.
    return pd.to_numeric(series.astype(str).str.extract(r"^(\d+)", expand=False), errors="coerce").astype("Int64")


def _normalize_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    chunk.columns = [c.strip().lower() for c in chunk.columns]
    chunk = chunk.drop(columns=[c for c in chunk.columns if c.startswith("unnamed")], errors="ignore")
    chunk = chunk.rename(columns=RENAME_MAP)
    for col in KEEP_COLUMNS:
        if col not in chunk.columns:
            chunk[col] = pd.NA
    chunk = chunk[KEEP_COLUMNS].copy()

    chunk["id_estacion_origen"] = _normalize_station_id(chunk["id_estacion_origen"])
    chunk["id_estacion_destino"] = _normalize_station_id(chunk["id_estacion_destino"])

    for lat_col, lon_col in [("lat_origen", "lon_origen"), ("lat_destino", "lon_destino")]:
        chunk[lat_col] = pd.to_numeric(chunk[lat_col], errors="coerce")
        chunk[lon_col] = pd.to_numeric(chunk[lon_col], errors="coerce")
        bad = ~chunk[lat_col].between(LAT_MIN, LAT_MAX) | ~chunk[lon_col].between(LON_MIN, LON_MAX)
        chunk.loc[bad, [lat_col, lon_col]] = pd.NA

    # dayfirst=True: algunos años publican fechas como DD/MM/YYYY. Sin esto,
    # pandas asume MM/DD/YYYY (inglés) y para día<=12 swapea día/mes en
    # silencio, corrompiendo el día de la semana calculado más abajo.
    chunk["fecha_origen"] = pd.to_datetime(chunk["fecha_origen"], errors="coerce", dayfirst=True)
    chunk["fecha_destino"] = pd.to_datetime(chunk["fecha_destino"], errors="coerce", dayfirst=True)
    return chunk


def iter_normalized_chunks(year: int):
    with _open_csv_stream(year) as stream:
        for raw_chunk in pd.read_csv(stream, chunksize=CHUNKSIZE, low_memory=False, on_bad_lines="skip"):
            yield _normalize_chunk(raw_chunk)


def build_station_lookup() -> pd.DataFrame:
    sums: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0])  # id -> [sum_lat, sum_lon, n]
    names: dict[str, Counter] = defaultdict(Counter)

    for year in YEARS:
        print(f"[estaciones] {year}...")
        try:
            for chunk in iter_normalized_chunks(year):
                for suf in ("origen", "destino"):
                    id_col, nom_col, lat_col, lon_col = f"id_estacion_{suf}", f"nombre_estacion_{suf}", f"lat_{suf}", f"lon_{suf}"
                    sub = chunk[[id_col, nom_col, lat_col, lon_col]].dropna()
                    if sub.empty:
                        continue

                    # agregación vectorizada por chunk (nada de loops fila-por-fila
                    # sobre los 100k registros del chunk, solo sobre las ~cientos
                    # de estaciones únicas que aparecen en él)
                    grouped = sub.groupby(id_col).agg(sum_lat=(lat_col, "sum"), sum_lon=(lon_col, "sum"), n=(lat_col, "size"))
                    for id_est, row in grouped.iterrows():
                        acc = sums[id_est]
                        acc[0] += row["sum_lat"]
                        acc[1] += row["sum_lon"]
                        acc[2] += row["n"]

                    for id_est, name_counts in sub.groupby(id_col)[nom_col].value_counts().groupby(level=0):
                        names[id_est].update(dict(name_counts.droplevel(0)))
        except requests.HTTPError as exc:
            print(f"  saltado ({exc})")

    rows = []
    for id_est, (sum_lat, sum_lon, n) in sums.items():
        nombre = names[id_est].most_common(1)[0][0] if names[id_est] else None
        rows.append({"id_estacion": id_est, "nombre_estacion": nombre, "lat": sum_lat / n, "lon": sum_lon / n, "n_obs": n})
    return pd.DataFrame(rows)


def build_trip_counts() -> pd.DataFrame:
    counts: Counter[tuple] = Counter()

    for year in YEARS:
        print(f"[conteo] {year}...")
        try:
            for chunk in iter_normalized_chunks(year):
                for suf, fecha_col, id_col in [("salida", "fecha_origen", "id_estacion_origen"), ("llegada", "fecha_destino", "id_estacion_destino")]:
                    sub = chunk[[id_col, fecha_col]].dropna()
                    if sub.empty:
                        continue
                    hora = sub[fecha_col].dt.hour
                    dow = sub[fecha_col].dt.dayofweek
                    key_df = pd.DataFrame({"id_estacion": sub[id_col], "tipo": suf, "hora": hora, "dia_semana": dow, "anio": year})
                    grouped = key_df.value_counts()
                    for key, n in grouped.items():
                        counts[key] += n
        except requests.HTTPError as exc:
            print(f"  saltado ({exc})")

    df = pd.DataFrame(
        [{"id_estacion": k[0], "tipo": k[1], "hora": k[2], "dia_semana": k[3], "anio": k[4], "viajes": n} for k, n in counts.items()]
    )
    return df


def main() -> None:
    print("=== Pasada 1: tabla canónica de estaciones ===")
    stations = build_station_lookup()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    stations.to_parquet(PROCESSED_DIR / "ecobici_estaciones.parquet", index=False)
    print(f"Estaciones: {len(stations)}")

    print("=== Pasada 2: viajes por estación / hora / día de semana ===")
    trip_counts = build_trip_counts()
    trip_counts.to_parquet(PROCESSED_DIR / "ecobici_viajes_agregado.parquet", index=False)
    print(f"Filas agregadas: {len(trip_counts)} (total viajes: {trip_counts['viajes'].sum()})")


if __name__ == "__main__":
    main()
