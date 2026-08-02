"""
Descarga y agrega los datos de Molinetes de Subte (subte-viajes-molinetes),
2013-2025: pasajeros por estación cada 15 minutos.

Mismas restricciones que ingest_ecobici.py (RAM de 3.4GB en la máquina de
desarrollo, un año grande descomprime a >1GB) — se lee todo en chunks y se
agrega directo a "pasajeros por estación/línea/hora/día de semana/año", sin
guardar cada registro de 15 minutos.

El dataset tiene dos esquemas según la época:
- 2013-2019 ("detallado"): una fila por MOLINETE individual, con
  ID_ESTACION numérico y desglose PAX_PAGOS/PAX_PASES_PAGOS/PAX_FREQ que
  suman a TOTAL.
- 2020 en adelante ("simple"): ya viene agregado por estación, con una
  columna CANTIDAD directa y sin id numérico (solo nombre de estación).

Ninguno de los dos esquemas trae coordenadas. Se geolocaliza cruzando
ESTACION+LINEA contra el dataset separado subte-estaciones (WKT POINT).
La referencia usa nombres compuestos/oficiales ("Almagro - Medrano",
"R.Scalabrini Ortiz") mientras molinetes usa el nombre corto de siempre
("MEDRANO", "SCALABRINI ORTIZ") — el match exacto solo, sin esto, fallaba
para ~32% del volumen. Se resuelve con matching por contención de tokens
+ expansión de abreviaturas (AV/PZA) + un puñado de alias manuales,
bajando el sin-matchear a ~3.2%. El resto son variantes de corrupción de
encoding en nombres con Ñ/Ü que difieren por año/archivo (ej. "AGA14ERO"
en vez de "AGÜERO") — se documenta como límite conocido en vez de
perseguir cada variante, no se inventan coordenadas.

Otra particularidad: desde 2022 el ZIP trae ~24-26 archivos separados
(uno por mes x grupo de líneas) en vez de un único CSV — hay que iterar
todos los miembros del zip, no asumir que hay uno solo.
"""

from __future__ import annotations

import csv
import re
import unicodedata
import zipfile
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import requests

BASE = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/sbase/subte-viajes-molinetes/{name}.zip"
YEAR_FILE_NAME = {2013: "molinetes-2013-junio-diciembre"}

ESTACIONES_URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/sbase/"
    "subte-estaciones/estaciones_de_subte.csv"
)

YEARS = [2013] + list(range(2014, 2026))

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "molinetes"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

CHUNKSIZE = 200_000

# El dataset cambia de esquema todos los años: "total" (2013,2015,2016...),
# "pax_total"/"pax_TOTAL" (2014, 2020...), y a veces "cantidad" (esquemas
# ya agregados). En vez de mapear caso por caso, se busca por substring.
TOTAL_PATTERNS = ("total", "cantidad")

# "linea" viene en 3 estilos según el año: "D" (plano), "LINEA_H"
# (mayúsculas + guión bajo), "LineaA" (mixto, sin separador). Se
# normaliza sacando cualquier variante del prefijo "linea".
LINEA_PREFIX_RE = re.compile(r"(?i)^linea_?")


def _normalize_name(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9]+", " ", s).strip().upper()
    return s


def _raw_path(year: int) -> Path:
    name = YEAR_FILE_NAME.get(year, f"molinetes-{year}")
    return RAW_DIR / f"{name}.zip"


def _is_valid_cached_file(path: Path) -> bool:
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
        print(f"  {path.name} está corrupto, re-descargando...")
        path.unlink()

    name = YEAR_FILE_NAME.get(year, f"molinetes-{year}")
    url = BASE.format(name=name)
    print(f"  descargando {url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, timeout=300, stream=True) as resp:
        resp.raise_for_status()
        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    return path


@contextmanager
def _open_zip(year: int):
    path = _ensure_downloaded(year)
    zf = zipfile.ZipFile(path)
    try:
        yield zf
    finally:
        zf.close()


def _csv_members(zf: zipfile.ZipFile) -> list[str]:
    # La mayoría de los años traen un único CSV, pero 2025 lo publica
    # partido en ~26 archivos (uno por mes x grupo de líneas ABC/DEH/PM)
    # dentro del mismo zip. Se filtran entradas de directorio (size 0).
    return [n for n in zf.namelist() if not n.endswith("/") and zf.getinfo(n).file_size > 0]


def _find_total_col(columns: list[str]) -> str:
    # "pax_total"/"pax_TOTAL" contienen "total" como substring, igual que
    # el "total" plano — un solo chequeo cubre ambos. Se prioriza que
    # contenga "pax" si hay más de un candidato (evita matchear alguna
    # columna no relacionada que casualmente contenga "total").
    candidates = [c for c in columns if any(p in c for p in TOTAL_PATTERNS)]
    if not candidates:
        raise ValueError(f"no se encontró columna de total/cantidad en {columns}")
    candidates.sort(key=lambda c: ("pax" not in c, c))
    return candidates[0]


def _normalize_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    chunk.columns = [c.strip().lower() for c in chunk.columns]
    cols = list(chunk.columns)

    total_col = _find_total_col(cols)
    if "desde" in cols:
        hora = chunk["desde"].astype(str).str.split(":").str[0]
    elif "hora" in cols:
        hora = chunk["hora"]
    else:
        raise ValueError(f"no se encontró columna de hora en {cols}")

    out = pd.DataFrame({
        "fecha": chunk["fecha"],
        "hora": pd.to_numeric(hora, errors="coerce"),
        "estacion": chunk["estacion"],
        "linea": chunk["linea"].astype(str).str.replace(LINEA_PREFIX_RE, "", regex=True),
        "cantidad": pd.to_numeric(chunk[total_col], errors="coerce"),
    })

    # dayfirst=True: las fechas vienen ambiguas en varios años (ej.
    # "3/1/2020"). Ver misma nota en ingest_ecobici.py.
    out["fecha"] = pd.to_datetime(out["fecha"], errors="coerce", dayfirst=True)
    out["estacion_norm"] = out["estacion"].map(_normalize_name)
    out["linea_norm"] = out["linea"].map(_normalize_name)
    out = out.dropna(subset=["fecha", "hora", "cantidad"])
    return out


_BOM = b"\xef\xbb\xbf"


def _strip_bom(stream):
    # Algunos años (ej. 2023) traen BOM UTF-8 al inicio del archivo. Con
    # encoding="latin-1" (necesario porque otros años no son UTF-8 válido)
    # el BOM no se reconoce como tal y sus 3 bytes quedan pegados como
    # basura al nombre de la primera columna. ZipExtFile soporta peek(),
    # así que se puede mirar sin consumir y descartar solo si corresponde
    # — a diferencia de envolver el stream en una clase propia, esto no
    # rompe la detección de encoding que hace pandas puertas adentro.
    if stream.peek(len(_BOM))[: len(_BOM)] == _BOM:
        stream.read(len(_BOM))
    return stream


def _detect_sep(stream) -> str:
    # El delimitador cambia entre "," y ";" según el año (mismo esquema de
    # columnas, distinto separador — ej. 2015 con coma, 2021 con punto y
    # coma). peek() no consume nada del stream, así que se puede detectar
    # sin gastar la apertura en una lectura descartable.
    sample = stream.peek(4096).decode("latin-1", errors="replace")
    first_line = sample.split("\n", 1)[0]
    return ";" if first_line.count(";") > first_line.count(",") else ","


def iter_normalized_chunks(year: int):
    with _open_zip(year) as zf:
        for member in _csv_members(zf):
            with zf.open(member) as stream:
                stream = _strip_bom(stream)
                sep = _detect_sep(stream)
                # Algunos años (ej. 2022+) envuelven la fila entera en un
                # solo par de comillas — "FECHA;DESDE;...;pax_TOTAL" — en
                # vez de citar campo por campo. Con el manejo de comillas
                # activo, pandas lo lee como una sola columna gigante en
                # vez de separar por ";". Se desactiva el quoting y se
                # limpian las comillas sueltas que quedan pegadas al
                # primer/último campo de cada fila.
                for raw_chunk in pd.read_csv(
                    stream, sep=sep, chunksize=CHUNKSIZE, low_memory=False,
                    on_bad_lines="skip", encoding="latin-1", quoting=csv.QUOTE_NONE,
                ):
                    raw_chunk.columns = [c.strip('"') for c in raw_chunk.columns]
                    for col in raw_chunk.select_dtypes(include="object").columns:
                        raw_chunk[col] = raw_chunk[col].str.strip('"')
                    yield _normalize_chunk(raw_chunk)


def build_station_lookup() -> pd.DataFrame:
    resp = requests.get(ESTACIONES_URL, timeout=60)
    resp.raise_for_status()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "estaciones_de_subte.csv").write_bytes(resp.content)

    df = pd.read_csv(RAW_DIR / "estaciones_de_subte.csv", encoding="utf-8-sig")
    df.columns = [c.strip().lower() for c in df.columns]

    coords = df["geometry"].str.extract(r"POINT \(([\-0-9\.]+) ([\-0-9\.]+)\)").astype(float)
    df["lon"] = coords[0]
    df["lat"] = coords[1]
    df["estacion_norm"] = df["estacion"].map(_normalize_name)
    df["linea_norm"] = df["linea"].map(_normalize_name)
    return df[["estacion", "linea", "estacion_norm", "linea_norm", "lat", "lon"]]


# La referencia de estaciones usa nombres compuestos/oficiales (ej.
# "Almagro - Medrano", "R.Scalabrini Ortiz", "Congreso - Pdte. Dr. Raúl
# Alfonsín") mientras molinetes usa el nombre corto de siempre ("MEDRANO",
# "SCALABRINI ORTIZ", "CONGRESO"). El match exacto fallaba para ~32% del
# volumen total. Se resuelve por contención de conjunto de palabras
# (ignorando "DE/DEL/LA/LOS/LAS"), cacheado por clave única.
_STOPWORDS = {"DE", "DEL", "LA", "LOS", "LAS", "Y"}

# Abreviaturas frecuentes en un lado u otro del dataset ("AV" vs
# "AVENIDA", "PZA" vs "PLAZA") que rompen el matching por tokens si no se
# normalizan primero.
_ABBREVIATIONS = {"AV": "AVENIDA", "AVDA": "AVENIDA", "PZA": "PLAZA"}

# Casos que ni el matching por tokens ni las abreviaturas resuelven,
# porque la referencia abrevia el nombre de pila (ej. "C. Pellegrini" vs
# "Carlos Pellegrini" — "C" y "CARLOS" no comparten tokens).
_MANUAL_ALIASES = {
    ("CARLOS PELLEGRINI", "B"): "C PELLEGRINI",
}


def _tokens(s: str) -> set[str]:
    return {_ABBREVIATIONS.get(w, w) for w in s.split() if w not in _STOPWORDS}


def _fuzzy_match(est_norm: str, candidatos: list[str]) -> str | None:
    m_tokens = _tokens(est_norm)
    if not m_tokens:
        return None
    best, best_size = None, None
    for cand in candidatos:
        c_tokens = _tokens(cand)
        if m_tokens <= c_tokens or c_tokens <= m_tokens:
            if best is None or len(c_tokens) < best_size:
                best, best_size = cand, len(c_tokens)
    return best


def build_trip_counts(stations: pd.DataFrame) -> tuple[pd.DataFrame, Counter]:
    counts: Counter[tuple] = Counter()
    unmatched: Counter[tuple] = Counter()
    known_keys = set(zip(stations["estacion_norm"], stations["linea_norm"]))
    stations_by_linea = stations.groupby("linea_norm")["estacion_norm"].apply(list).to_dict()
    alias_cache: dict[tuple, tuple | None] = {}

    def resolve(est_norm: str, lin_norm: str) -> tuple | None:
        key = (est_norm, lin_norm)
        if key in known_keys:
            return key
        if key in alias_cache:
            return alias_cache[key]
        match = _MANUAL_ALIASES.get(key) or _fuzzy_match(est_norm, stations_by_linea.get(lin_norm, []))
        resolved = (match, lin_norm) if match else None
        alias_cache[key] = resolved
        return resolved

    for year in YEARS:
        print(f"[molinetes] {year}...")
        try:
            for chunk in iter_normalized_chunks(year):
                for key, group_total in chunk.groupby(["estacion_norm", "linea_norm", "hora", chunk["fecha"].dt.dayofweek])["cantidad"].sum().items():
                    est_norm, lin_norm, hora, dow = key
                    resolved = resolve(est_norm, lin_norm)
                    if resolved is None:
                        unmatched[(est_norm, lin_norm)] += int(group_total)
                        continue
                    counts[(resolved[0], resolved[1], hora, dow, year)] += int(group_total)
        except requests.HTTPError as exc:
            print(f"  saltado ({exc})")

    df = pd.DataFrame(
        [
            {"estacion_norm": k[0], "linea_norm": k[1], "hora": k[2], "dia_semana": k[3], "anio": k[4], "pasajeros": n}
            for k, n in counts.items()
        ]
    )
    return df, unmatched


def main() -> None:
    print("=== Tabla de referencia de estaciones de subte ===")
    stations = build_station_lookup()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    stations.to_parquet(PROCESSED_DIR / "molinetes_estaciones.parquet", index=False)
    print(f"Estaciones de referencia: {len(stations)}")

    print("=== Pasajeros por estación / línea / hora / día de semana ===")
    trip_counts, unmatched = build_trip_counts(stations)

    merged = trip_counts.merge(
        stations[["estacion_norm", "linea_norm", "estacion", "linea", "lat", "lon"]],
        on=["estacion_norm", "linea_norm"],
        how="left",
    )
    merged.to_parquet(PROCESSED_DIR / "molinetes_agregado.parquet", index=False)
    print(f"Filas agregadas: {len(merged)} (total pasajeros: {merged['pasajeros'].sum()})")

    if unmatched:
        total_unmatched = sum(unmatched.values())
        total_matched = merged["pasajeros"].sum()
        print(f"Sin geolocalizar: {len(unmatched)} combinaciones estación/línea, {total_unmatched} pasajeros "
              f"({total_unmatched / (total_unmatched + total_matched):.1%} del total)")
        print("Top 10 sin matchear:", unmatched.most_common(10))


if __name__ == "__main__":
    main()
