"""
Utilidades geoespaciales compartidas entre scripts de pipeline/.

GCBA usa DOS sistemas de coordenadas planas distintos según el dataset,
sin documentarlo en los metadatos — se descubrió a fuerza de que la
reproyección diera resultados absurdos (escuelas/hospitales cayendo 90km
al oeste de CABA) y tener que recalibrar contra el geocodificador oficial
(ws.usig.buenosaires.gob.ar):

- GKBA (Gauss-Krüger CABA 2019, "oficial" desde 2019): x_0=100000,
  y_0=100000. Lo usa siniestros_viales (columna geocodificacion_plana).
  Verificado con error sub-métrico contra un punto conocido.
- Sistema viejo ("0 de Flores", pre-2019): x_0≈19968, y_0≈70099 sobre el
  mismo meridiano central. Lo usan escuelas y hospitales. Calibrado
  cruzando dos direcciones reales contra el geocodificador oficial de
  GCBA — da ~100m de error consistente (probable diferencia de datum
  Campo Inchauspe/Hayford vs. GRS80 de la época, no vale la pena resolver
  con más precisión: 100m es menos que una cuadra, suficiente para un
  feature de riesgo por zona).

El código EPSG que GCBA documenta públicamente para el sistema nuevo
(9497) no existe en las bases de PROJ/epsg.io — de ahí que ninguno de los
dos esté definido como EPSG estándar, sino como proj4 a mano.
"""

from __future__ import annotations

import pandas as pd
from pyproj import Transformer

GKBA_PROJ4 = (
    "+proj=tmerc +lat_0=-34.6292666666667 +lon_0=-58.4633083333333 "
    "+k=1 +x_0=100000 +y_0=100000 +ellps=GRS80 +units=m +no_defs"
)

# Sistema legacy ("0 de Flores") usado por escuelas/hospitales — ver nota arriba.
GKBA_LEGACY_PROJ4 = (
    "+proj=tmerc +lat_0=-34.6292666666667 +lon_0=-58.4633083333333 "
    "+k=1 +x_0=19968.069878044025 +y_0=70098.59294578151 +ellps=GRS80 +units=m +no_defs"
)

_transformer = Transformer.from_crs(GKBA_PROJ4, "EPSG:4326", always_xy=True)
_transformer_legacy = Transformer.from_crs(GKBA_LEGACY_PROJ4, "EPSG:4326", always_xy=True)


def _point_to_latlon(wkt_point: pd.Series, transformer: Transformer) -> tuple[pd.Series, pd.Series]:
    coords = wkt_point.str.extract(r"POINT \(([\-0-9\.]+) ([\-0-9\.]+)\)").astype(float)
    lon, lat = transformer.transform(coords[0].to_numpy(), coords[1].to_numpy())
    return pd.Series(lat, index=wkt_point.index), pd.Series(lon, index=wkt_point.index)


def gkba_point_to_latlon(wkt_point: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Convierte WKT 'POINT (x y)' en GKBA (sistema nuevo, 2019+) a (lat, lon)."""
    return _point_to_latlon(wkt_point, _transformer)


def gkba_legacy_point_to_latlon(wkt_point: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Convierte WKT 'POINT (x y)' en el sistema viejo ("0 de Flores") a (lat, lon).
    Precisión ~100m — ver nota del módulo."""
    return _point_to_latlon(wkt_point, _transformer_legacy)
