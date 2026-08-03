"""
Utilidades H3 compartidas por los scripts de src/etl/ y src/model_core/
(CAPA 0 de arquitectura-sige-ba.pdf).

Usa h3-py v4 (API `latlng_to_cell`/`polygon_to_cells`/`cell_to_boundary`,
distinta de la v3 `geo_to_h3`/`polyfill` que aparece en tutoriales viejos).
Ojo con el orden de coordenadas: h3 trabaja en (lat, lng); shapely/geopandas
en (lon, lat) — hay que transponer en cada dirección.
"""

from __future__ import annotations

import h3
import pandas as pd
from shapely.geometry import Polygon

RESOLUCION_MODELO = 8  # ~0.7 km², ~300 hexágonos en CABA — grano de entrenamiento.
RESOLUCION_VISUAL = 9  # ~0.1 km² — solo para el dashboard, no para entrenar.


def turno_desde_hora(hora: pd.Series) -> pd.Series:
    """Mañana 06-14 / Tarde 14-22 / Noche 22-02 / Madrugada 02-06 (sección 1.2).

    Acepta hora numérica (0-23, como "franja" de delitos) o texto "HH:MM:SS"
    (como "hora_siniestro") — se detecta y parsea según haga falta.
    """
    numerica = pd.to_numeric(hora, errors="coerce")
    if numerica.isna().mean() > 0.5:  # mayormente no numérico -> asumir "HH:MM:SS"
        numerica = pd.to_numeric(hora.astype(str).str.split(":").str[0], errors="coerce")
    h = numerica % 24
    return pd.cut(
        h,
        bins=[-0.1, 2, 6, 14, 22, 24],
        labels=["Noche", "Madrugada", "Mañana", "Tarde", "Noche"],
        ordered=False,
    ).astype(str)


def polygon_a_h3shape(poly) -> "h3.LatLngPoly":
    """Convierte un shapely Polygon (lon,lat) al LatLngPoly (lat,lng) que espera h3."""
    exterior = [(y, x) for x, y in poly.exterior.coords]
    holes = [[(y, x) for x, y in ring.coords] for ring in poly.interiors]
    return h3.LatLngPoly(exterior, *holes)


def hex_a_shapely_polygon(hex_id: str) -> Polygon:
    boundary = h3.cell_to_boundary(hex_id)  # lista de (lat, lng)
    return Polygon([(lng, lat) for lat, lng in boundary])


def asignar_hex_id(df: pd.DataFrame, lat_col: str, lon_col: str, resolution: int = RESOLUCION_MODELO) -> pd.Series:
    """hex_id por fila a partir de columnas lat/lon. Filas con lat/lon nulo -> hex_id nulo.

    Algunos datasets de origen (ej. siniestros_hechos) guardan lat/lon como
    string en vez de float — se castea acá en vez de asumir el dtype.
    """
    lat = pd.to_numeric(df[lat_col], errors="coerce")
    lon = pd.to_numeric(df[lon_col], errors="coerce")

    def _cell(la, lo):
        if pd.isna(la) or pd.isna(lo):
            return None
        return h3.latlng_to_cell(la, lo, resolution)

    return pd.Series([_cell(la, lo) for la, lo in zip(lat, lon)], index=df.index)
