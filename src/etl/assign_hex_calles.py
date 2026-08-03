"""
CAPA 0, pasos 4-5 de arquitectura-sige-ba.pdf:

- calles: hex_id por el punto medio de cada tramo (ya calculado como
  centroide del LINESTRING en pipeline/ingest_calles.py, se reutiliza en
  vez de recalcular) — la jerarquía vial queda como atributo del hex.
- accesos_autopista: hex_id propio + el tramo de calle troncal (jerarquía
  "VÍA TRONCAL") más cercano, para poder recorrer corredores desde cada
  acceso en el Módulo C más adelante. La distancia se calcula reproyectando
  a POSGAR 2007 faja 5 (EPSG:5347, metros) en vez de en grados, para que
  "más cercano" tenga sentido físico real.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

from hex_utils import asignar_hex_id

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
FEATURES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "features"

CRS_GEO = "EPSG:4326"
CRS_METROS = "EPSG:5347"


def main() -> None:
    calles = pd.read_parquet(PROCESSED_DIR / "calles.parquet")
    calles["hex_id"] = asignar_hex_id(calles, "lat", "lon")
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    calles.to_parquet(FEATURES_DIR / "calles_hex.parquet", index=False)
    print(f"calles: {len(calles)} tramos con hex_id ({calles['hex_id'].nunique()} hexágonos distintos)")

    accesos = pd.read_parquet(PROCESSED_DIR / "accesos_autopistas.parquet")
    accesos["hex_id"] = asignar_hex_id(accesos, "lat", "lon")

    troncales = calles[calles["jerarquia"] == "VÍA TRONCAL"].dropna(subset=["lat", "lon"])
    accesos_gdf = gpd.GeoDataFrame(
        accesos, geometry=gpd.points_from_xy(accesos["lon"], accesos["lat"]), crs=CRS_GEO
    ).to_crs(CRS_METROS)
    troncales_gdf = gpd.GeoDataFrame(
        troncales[["id", "nombre"]].rename(
            columns={"id": "id_calle_troncal_cercana", "nombre": "nombre_calle_troncal_cercana"}
        ),
        geometry=gpd.points_from_xy(troncales["lon"], troncales["lat"]), crs=CRS_GEO,
    ).to_crs(CRS_METROS)

    cercano = gpd.sjoin_nearest(
        accesos_gdf, troncales_gdf, how="left", distance_col="distancia_calle_troncal_m"
    ).drop(columns="index_right")
    cercano = cercano.drop(columns="geometry").drop_duplicates(subset="id_peaje")

    cercano.to_parquet(FEATURES_DIR / "accesos_autopistas_hex.parquet", index=False)
    print(f"accesos: {len(cercano)} filas con hex_id + calle troncal más cercana")
    print(cercano[["nombre", "nombre_calle_troncal_cercana", "distancia_calle_troncal_m"]])


if __name__ == "__main__":
    main()
