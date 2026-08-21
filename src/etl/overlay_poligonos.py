"""
CAPA 0, filas 7-8-17 pendientes de la tabla de cruces (arquitectura-sige-ba.pdf) —
las tres son overlay de polígono contra hex_maestra, no point-in-hex simple,
por eso quedaron afuera de assign_hex_puntual.py:

- espacios_verdes -> % de área verde por hex (overlay real, un hex puede
  tocar varias plazas o ninguna).
- comisarias (zona de patrullaje) -> qué comisaría cubre la mayor parte
  de cada hex (overlay + argmax de área de intersección, no solo el
  centroide, porque el borde de un hex puede caer en otra zona).
- población por hex -> se prorratea DENTRO del barrio ya asignado a cada
  hex en hex_maestra (por centroide), proporcional al área de cada hex —
  no hace falta un overlay hex-contra-barrio real porque H3 a resolución
  8 da hexágonos de área casi idéntica (~0,7 km² cada uno); prorratear por
  área terminaría siendo casi lo mismo que dividir por cantidad de hex,
  pero se calcula con el área real de cada uno para no asumirlo.

- NBI por hex -> interpolacion areal desde los radios censales (overlay
  real, no el prorrateo por barrio): el NBI varia mucho dentro de un mismo
  barrio y promediarlo borraria la senal.

Todo en EPSG:5347 (POSGAR 2007 faja 5) para que las áreas sean metros
cuadrados reales, no grados².
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import wkt

PROCESSED = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"

CRS_GEO = "EPSG:4326"
CRS_METROS = "EPSG:5347"


def cargar_gdf(path: Path, cols: list[str]) -> gpd.GeoDataFrame:
    df = pd.read_parquet(path)
    gdf = gpd.GeoDataFrame(df[cols], geometry=df["geometry_wkt"].map(wkt.loads), crs=CRS_GEO)
    return gdf.to_crs(CRS_METROS)


def espacios_verdes_por_hex(hex_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    verdes = cargar_gdf(PROCESSED / "espacios_verdes.parquet", ["id"])
    inter = gpd.overlay(hex_gdf[["hex_id", "geometry"]], verdes, how="intersection")
    inter["area_m2"] = inter.geometry.area
    area_verde = inter.groupby("hex_id")["area_m2"].sum()

    resultado = hex_gdf[["hex_id"]].copy()
    resultado["area_hex_m2"] = hex_gdf.geometry.area
    resultado["area_verde_m2"] = resultado["hex_id"].map(area_verde).fillna(0)
    resultado["pct_espacio_verde"] = (resultado["area_verde_m2"] / resultado["area_hex_m2"]).clip(upper=1.0)
    return resultado[["hex_id", "pct_espacio_verde"]]


def comisaria_por_hex(hex_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    zonas = cargar_gdf(PROCESSED / "comisarias.parquet", ["id_area", "nombre"])
    inter = gpd.overlay(hex_gdf[["hex_id", "geometry"]], zonas, how="intersection")
    inter["area_m2"] = inter.geometry.area
    idx_max = inter.groupby("hex_id")["area_m2"].idxmax()
    ganador = inter.loc[idx_max, ["hex_id", "id_area", "nombre"]].rename(
        columns={"id_area": "comisaria_id", "nombre": "comisaria_nombre"}
    )
    print(f"Hexágonos sin ninguna comisaría de patrullaje asignada: {hex_gdf['hex_id'].nunique() - ganador['hex_id'].nunique()}")
    return ganador


def poblacion_por_hex(hex_gdf: gpd.GeoDataFrame, hex_maestra: pd.DataFrame) -> pd.DataFrame:
    poblacion_barrio = pd.read_parquet(PROCESSED / "poblacion_barrio.parquet")
    # poblacion_barrio.barrio está en MAYÚSCULAS (fuente original), barrio_id en Title Case
    poblacion_barrio["barrio_upper"] = poblacion_barrio["barrio"]

    resultado = hex_maestra[["hex_id", "barrio_id"]].copy()
    resultado["area_hex_m2"] = hex_gdf.set_index("hex_id").loc[resultado["hex_id"], "geometry"].area.to_numpy()
    resultado["barrio_upper"] = resultado["barrio_id"].str.upper()

    # merge() devuelve un DataFrame con índice nuevo (0..n-1) que NO respeta
    # el orden de filas original — calcular area_total_por_barrio antes del
    # merge y usarlo después provoca una desalineación silenciosa (pandas
    # alinea por índice, no por posición). Todo el cálculo tiene que vivir
    # en el mismo dataframe sin un merge en el medio.
    resultado = resultado.merge(poblacion_barrio[["barrio_upper", "poblacion"]], on="barrio_upper", how="left")
    area_total_por_barrio = resultado.groupby("barrio_upper")["area_hex_m2"].transform("sum")
    resultado["poblacion_hex"] = resultado["poblacion"] * (resultado["area_hex_m2"] / area_total_por_barrio)
    return resultado[["hex_id", "poblacion_hex"]]


def nbi_por_hex(hex_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """Hogares y hogares con NBI por hexagono, por interpolacion areal.

    Aca si conviene un overlay real contra los radios censales, y no el atajo
    que usa `poblacion_por_hex` de prorratear dentro del barrio: el radio es
    la unidad mas fina que existe (~800 habitantes contra ~7.200 de un hex) y
    el NBI **varia muchisimo dentro de un mismo barrio** —es justo lo que
    mide—. Prorratear el promedio del barrio borraria esa variacion, que es
    la senal entera.

    El supuesto de la interpolacion areal es que los hogares estan repartidos
    de forma pareja dentro de cada radio. A esta escala es razonable: un radio
    censal se dibuja precisamente para ser homogeneo.

    Se devuelve el conteo y no el porcentaje: un porcentaje por hexagono no se
    puede volver a agregar sin los pesos, y el uso de esta tabla es sumar
    hogares sobre conjuntos de hexagonos (los que cubre un plan de patrullas).
    """
    radios = pd.read_parquet(PROCESSED / "radios_censales.parquet")
    gdf = gpd.GeoDataFrame(
        radios[["id_radio", "hogares_total", "hogares_con_nbi"]],
        geometry=radios["geometry_wkt"].map(wkt.loads), crs=CRS_GEO).to_crs(CRS_METROS)
    gdf["area_radio_m2"] = gdf.geometry.area

    inter = gpd.overlay(hex_gdf[["hex_id", "geometry"]], gdf, how="intersection")
    frac = inter.geometry.area / inter["area_radio_m2"]
    inter["hogares_hex"] = inter["hogares_total"] * frac
    inter["hogares_nbi_hex"] = inter["hogares_con_nbi"] * frac

    return (inter.groupby("hex_id")[["hogares_hex", "hogares_nbi_hex"]].sum()
            .reindex(hex_gdf["hex_id"]).fillna(0).reset_index())


def main() -> None:
    hex_maestra = pd.read_parquet(FEATURES / "hex_maestra.parquet").dropna(subset=["barrio_id"])
    hex_gdf = cargar_gdf(FEATURES / "hex_maestra.parquet", ["hex_id"])
    hex_gdf = hex_gdf[hex_gdf["hex_id"].isin(hex_maestra["hex_id"])]

    verdes = espacios_verdes_por_hex(hex_gdf)
    print(f"Espacios verdes: {(verdes['pct_espacio_verde'] > 0).sum()} de {len(verdes)} hex con algo de verde, "
          f"media {verdes['pct_espacio_verde'].mean():.1%}")
    verdes.to_parquet(FEATURES / "hex_espacios_verdes.parquet", index=False)

    comisarias = comisaria_por_hex(hex_gdf)
    comisarias.to_parquet(FEATURES / "hex_comisaria_patrullaje.parquet", index=False)
    print(f"Comisarías: {comisarias['hex_id'].nunique()} hex con zona de patrullaje asignada")

    poblacion = poblacion_por_hex(hex_gdf, hex_maestra)
    print(f"Población por hex: suma total {poblacion['poblacion_hex'].sum():,.0f} "
          f"(vs. {pd.read_parquet(PROCESSED / 'poblacion_barrio.parquet')['poblacion'].sum():,.0f} real)")
    poblacion.to_parquet(FEATURES / "hex_poblacion.parquet", index=False)

    nbi = nbi_por_hex(hex_gdf)
    radios = pd.read_parquet(PROCESSED / "radios_censales.parquet")
    print(f"NBI por hex: {nbi['hogares_hex'].sum():,.0f} hogares "
          f"(vs. {radios['hogares_total'].sum():,.0f} en los radios), "
          f"{nbi['hogares_nbi_hex'].sum():,.0f} con NBI "
          f"({nbi['hogares_nbi_hex'].sum() / nbi['hogares_hex'].sum():.2%})")
    nbi.to_parquet(FEATURES / "hex_nbi.parquet", index=False)

    print("\nGuardado: hex_espacios_verdes.parquet, hex_comisaria_patrullaje.parquet, "
          "hex_poblacion.parquet, hex_nbi.parquet")


if __name__ == "__main__":
    main()
