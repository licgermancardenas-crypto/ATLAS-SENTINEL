"""
CAPA 1 v2 (arquitectura-sige-ba.pdf, sección 8, roadmap paso 3): suma
variables exógenas a training_table.parquet (v1) y guarda
training_table_v2.parquet, para comparar Recall@K contra v1 sin exógenas.

- clima: join directo por fecha (no espacial, sección "13" de la tabla de
  cruces) — mismo lluvia/temperatura para toda la ciudad ese día.
- eventos_masivos 2019 (con lat/lon): point-in-hex + fecha -> flag por hex.
- eventos_masivos 2023-2026 (solo barrio): join por barrio_id + fecha ->
  flag a resolución de barrio, se propaga a todos los hex de ese barrio
  (hex_maestra ya trae barrio_id).
- estadios: buffer 500m desde el centroide de cada hex (reproyectado a
  EPSG:5347 para que "500m" sea metros reales, no grados) -> flag
  "cerca_estadio", estático por hex.

Los flags de evento son por día completo (no por turno) porque ni 2019 ni
2023-2026 traen el horario cruzado con turno de forma confiable — igual
que lo especifica el documento ("flag evento ese día en ese hex/barrio").
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import h3
import pandas as pd

PROCESSED = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"

CRS_GEO = "EPSG:4326"
CRS_METROS = "EPSG:5347"
BUFFER_ESTADIO_M = 500


def agregar_clima(tabla: pd.DataFrame) -> pd.DataFrame:
    clima = pd.read_parquet(PROCESSED / "clima_diario.parquet")[["fecha", "temp_media_c", "lluvia"]]
    tabla = tabla.merge(clima, on="fecha", how="left")
    print(f"Clima: {tabla['temp_media_c'].notna().mean():.1%} de filas con dato (el resto son días sin procesar en NASA POWER)")
    return tabla


def agregar_eventos(tabla: pd.DataFrame, hex_maestra: pd.DataFrame) -> pd.DataFrame:
    eventos = pd.read_parquet(PROCESSED / "eventos_masivos.parquet")

    con_geo = eventos.dropna(subset=["lat", "lon", "fecha"]).copy()
    con_geo["hex_id"] = con_geo.apply(lambda r: h3.latlng_to_cell(r["lat"], r["lon"], 8), axis=1)
    evento_por_hex_fecha = con_geo[["hex_id", "fecha"]].drop_duplicates()
    evento_por_hex_fecha["evento_en_hex"] = True

    tabla = tabla.merge(evento_por_hex_fecha, on=["hex_id", "fecha"], how="left")
    tabla["evento_en_hex"] = tabla["evento_en_hex"].fillna(False)

    # eventos_masivos.barrio viene en MAYÚSCULAS, hex_maestra.barrio_id en Title Case
    # (cada uno heredó el casing de su fuente de origen) — se normaliza para el join.
    solo_barrio = eventos.dropna(subset=["barrio", "fecha"])
    evento_por_barrio_fecha = solo_barrio[["barrio", "fecha"]].drop_duplicates()
    evento_por_barrio_fecha["barrio"] = evento_por_barrio_fecha["barrio"].str.upper()
    evento_por_barrio_fecha["evento_en_barrio"] = True

    tabla = tabla.merge(hex_maestra[["hex_id", "barrio_id"]], on="hex_id", how="left")
    tabla["barrio_upper"] = tabla["barrio_id"].str.upper()
    tabla = tabla.merge(
        evento_por_barrio_fecha, left_on=["barrio_upper", "fecha"], right_on=["barrio", "fecha"], how="left"
    ).drop(columns=["barrio", "barrio_upper"])
    tabla["evento_en_barrio"] = tabla["evento_en_barrio"].fillna(False)
    tabla = tabla.drop(columns="barrio_id")

    print(f"Eventos: {tabla['evento_en_hex'].mean():.3%} filas con evento en el hex (2019), "
          f"{tabla['evento_en_barrio'].mean():.3%} con evento en el barrio (2023-2026)")
    return tabla


def agregar_cerca_estadio(tabla: pd.DataFrame, hex_maestra: pd.DataFrame) -> pd.DataFrame:
    estadios = pd.read_parquet(PROCESSED / "estadios.parquet").dropna(subset=["lat", "lon"])
    estadios_gdf = gpd.GeoDataFrame(
        estadios, geometry=gpd.points_from_xy(estadios["lon"], estadios["lat"]), crs=CRS_GEO
    ).to_crs(CRS_METROS)

    hex_gdf = gpd.GeoDataFrame(
        hex_maestra[["hex_id"]],
        geometry=gpd.points_from_xy(hex_maestra["lon"], hex_maestra["lat"]), crs=CRS_GEO,
    ).to_crs(CRS_METROS)

    cercano = gpd.sjoin_nearest(hex_gdf, estadios_gdf[["geometry"]], how="left", distance_col="dist_estadio_m")
    cercano = cercano.drop_duplicates(subset="hex_id")
    cercano["cerca_estadio"] = cercano["dist_estadio_m"] <= BUFFER_ESTADIO_M

    tabla = tabla.merge(cercano[["hex_id", "cerca_estadio"]], on="hex_id", how="left")
    tabla["cerca_estadio"] = tabla["cerca_estadio"].fillna(False)
    n_hex_cerca = cercano.loc[cercano["cerca_estadio"], "hex_id"].nunique()
    print(f"Estadios: {n_hex_cerca} hexágonos dentro de {BUFFER_ESTADIO_M}m de un estadio")
    return tabla


def main() -> None:
    tabla = pd.read_parquet(FEATURES / "training_table.parquet")
    hex_maestra = pd.read_parquet(FEATURES / "hex_maestra.parquet")

    tabla = agregar_clima(tabla)
    tabla = agregar_eventos(tabla, hex_maestra)
    tabla = agregar_cerca_estadio(tabla, hex_maestra)

    tabla.to_parquet(FEATURES / "training_table_v2.parquet", index=False)
    print(f"\nGuardado: training_table_v2.parquet, {len(tabla):,} filas")


if __name__ == "__main__":
    main()
