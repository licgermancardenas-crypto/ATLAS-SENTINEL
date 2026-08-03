"""
CAPA 0, pasos 1-2 de arquitectura-sige-ba.pdf: genera la grilla H3-8 sobre
CABA y la tabla hex_maestra (hex_id, geometry, centroid, barrio_id,
radio_censal_id, comuna_id) — es la base de todo lo demás, sin esto no
se puede avanzar a Capa 1.

El polígono de CABA no viene de un dataset propio: se calcula como la
unión de los 48 barrios de barrios.parquet (los barrios ya cubren toda la
ciudad sin huecos, no hace falta bajar un dataset de "límite CABA" aparte).
Tampoco existe comunas.parquet — comuna sale directo del barrio que
contiene a cada hexágono (barrios.parquet ya trae comuna por fila).

barrio_id / radio_censal_id se asignan por el centroide del hexágono
(point-in-polygon), no por el hexágono completo — un hexágono de borde
puede pisar dos barrios, se lo asigna al que contiene su centro.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import wkt
from shapely.ops import unary_union

from hex_utils import RESOLUCION_MODELO, hex_a_shapely_polygon, polygon_a_h3shape
import h3

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
FEATURES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "features"

CRS = "EPSG:4326"


def main() -> None:
    barrios = pd.read_parquet(PROCESSED_DIR / "barrios.parquet")
    barrios_gdf = gpd.GeoDataFrame(
        barrios, geometry=barrios["geometry_wkt"].map(wkt.loads), crs=CRS
    )

    radios = pd.read_parquet(PROCESSED_DIR / "radios_censales.parquet")
    radios_gdf = gpd.GeoDataFrame(
        radios, geometry=radios["geometry_wkt"].map(wkt.loads), crs=CRS
    )

    caba_boundary = unary_union(barrios_gdf.geometry.to_list())
    polys = caba_boundary.geoms if caba_boundary.geom_type == "MultiPolygon" else [caba_boundary]

    # contain="overlap" (no el "center" por default) — con "center" quedaban 1-6%
    # de los puntos de delitos/siniestros/alumbrado fuera de la grilla, porque caen
    # en hexágonos de borde/costa cuyo CENTRO está just afuera del polígono de CABA
    # aunque el punto en sí esté adentro. "overlap" incluye cualquier hexágono que
    # toque el polígono, aunque sea parcialmente.
    hex_ids: set[str] = set()
    for poly in polys:
        hex_ids |= set(h3.polygon_to_cells_experimental(
            polygon_a_h3shape(poly), RESOLUCION_MODELO, contain="overlap"
        ))
    print(f"Hexágonos H3-{RESOLUCION_MODELO} generados sobre CABA: {len(hex_ids)}")

    hex_df = pd.DataFrame({"hex_id": sorted(hex_ids)})
    hex_df["geometry"] = hex_df["hex_id"].map(hex_a_shapely_polygon)
    hex_gdf = gpd.GeoDataFrame(hex_df, geometry="geometry", crs=CRS)
    hex_gdf["lat"] = hex_gdf["hex_id"].map(lambda h: h3.cell_to_latlng(h)[0])
    hex_gdf["lon"] = hex_gdf["hex_id"].map(lambda h: h3.cell_to_latlng(h)[1])

    centroides = gpd.GeoDataFrame(
        hex_gdf[["hex_id"]], geometry=gpd.points_from_xy(hex_gdf["lon"], hex_gdf["lat"]), crs=CRS
    )

    con_barrio = gpd.sjoin(
        centroides, barrios_gdf[["nombre", "comuna", "geometry"]],
        how="left", predicate="within",
    ).drop(columns="index_right")
    con_barrio = con_barrio.rename(columns={"nombre": "barrio_id", "comuna": "comuna_id"})
    con_barrio = con_barrio.drop_duplicates(subset="hex_id")  # por si un centroide cae justo en un borde compartido

    con_radio = gpd.sjoin(
        centroides, radios_gdf[["id_radio", "geometry"]],
        how="left", predicate="within",
    ).drop(columns="index_right")
    con_radio = con_radio.drop_duplicates(subset="hex_id").rename(columns={"id_radio": "radio_censal_id"})

    hex_gdf = hex_gdf.merge(con_barrio[["hex_id", "barrio_id", "comuna_id"]], on="hex_id", how="left")
    hex_gdf = hex_gdf.merge(con_radio[["hex_id", "radio_censal_id"]], on="hex_id", how="left")

    sin_barrio = hex_gdf["barrio_id"].isna().sum()
    sin_radio = hex_gdf["radio_censal_id"].isna().sum()
    print(f"Hexágonos sin barrio asignado (centro cae fuera de los 48 polígonos): {sin_barrio}")
    print(f"Hexágonos sin radio censal asignado: {sin_radio}")

    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    hex_gdf["geometry_wkt"] = hex_gdf["geometry"].map(lambda g: g.wkt)
    hex_gdf.drop(columns="geometry").to_parquet(FEATURES_DIR / "hex_maestra.parquet", index=False)
    print(f"Guardado: hex_maestra.parquet con {len(hex_gdf)} hexágonos")
    print(hex_gdf["comuna_id"].value_counts(dropna=False).sort_index())


if __name__ == "__main__":
    main()
