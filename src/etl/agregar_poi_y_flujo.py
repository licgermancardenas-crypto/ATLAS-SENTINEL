"""
P1 de la auditoría técnica externa (sección 4): escuelas, hospitales,
universidades, cajeros, y flujo peatonal de EcoBici/Molinetes se
cruzaron a hex_id en Capa 0 pero nunca llegaron al training table del
modelo núcleo — la mitad de Crime Pattern Theory (nodes/paths de
Brantingham & Brantingham) ausente del modelo pese a estar ya calculada.
Este script cierra ese cruce.

POIs: conteo dentro de un buffer de 300m del centroide de cada hex (no
"mismo hex", que subestima en los bordes — un hospital a 50m de un
hex pero del otro lado de la línea no debería contar cero). Buffer fijo
en vez de anillo H3 para que el resultado no dependa de la resolución de
la grilla.

Flujo peatonal: a diferencia de camaras/alumbrado (estáticos), EcoBici y
Molinetes tienen granularidad horaria — se agregan por hex×turno (no
solo por hex) usando el mismo `turno_desde_hora` que el resto del
pipeline, para que el feature sea "cuánta gente circula típicamente acá
en este turno", coherente con el grano del modelo.
"""

from __future__ import annotations

import sys
from itertools import product
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hex_utils import turno_desde_hora  # noqa: E402

PROCESSED = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"

CRS_GEO = "EPSG:4326"
CRS_METROS = "EPSG:5347"
RADIO_POI_M = 300

POIS = {
    "escuelas": ("escuelas_hex.parquet", "lat", "lon"),
    "hospitales": ("hospitales_hex.parquet", "lat", "lon"),
    "universidades": ("universidades_hex.parquet", "lat", "lon"),
    "cajeros": ("cajeros_hex.parquet", "lat", "long"),
}


def coords_metros(df: pd.DataFrame, col_lat: str, col_lon: str) -> gpd.GeoSeries:
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[col_lon], df[col_lat]), crs=CRS_GEO)
    return gdf.to_crs(CRS_METROS).geometry


def agregar_pois(hex_maestra: pd.DataFrame) -> pd.DataFrame:
    hex_xy = coords_metros(hex_maestra, "lat", "lon")
    hex_arr = hex_xy.get_coordinates().to_numpy()

    resultado = hex_maestra[["hex_id"]].copy()
    for nombre, (archivo, col_lat, col_lon) in POIS.items():
        poi = pd.read_parquet(FEATURES / archivo).dropna(subset=[col_lat, col_lon])
        poi_xy = coords_metros(poi, col_lat, col_lon).get_coordinates().to_numpy()

        conteo = []
        for x, y in hex_arr:
            dist2 = (poi_xy[:, 0] - x) ** 2 + (poi_xy[:, 1] - y) ** 2
            conteo.append(int((dist2 <= RADIO_POI_M ** 2).sum()))
        resultado[f"n_{nombre}_cerca"] = conteo
        print(f"  {nombre}: {sum(conteo)} en radio de {RADIO_POI_M}m sumando los {len(hex_maestra)} hex "
              f"(media {sum(conteo)/len(hex_maestra):.1f} por hex)")
    return resultado


def agregar_flujo(hex_maestra: pd.DataFrame) -> pd.DataFrame:
    ecobici_hex = pd.read_parquet(FEATURES / "ecobici_estaciones_hex.parquet")[["id_estacion", "hex_id"]]
    ecobici_viajes = pd.read_parquet(PROCESSED / "ecobici_viajes_agregado.parquet")
    ecobici_viajes["turno"] = turno_desde_hora(ecobici_viajes["hora"])
    ecobici_por_estacion_turno = ecobici_viajes.groupby(["id_estacion", "turno"])["viajes"].sum().reset_index()
    flujo_ecobici = ecobici_por_estacion_turno.merge(ecobici_hex, on="id_estacion", how="inner")
    flujo_ecobici = flujo_ecobici.groupby(["hex_id", "turno"])["viajes"].sum().reset_index()
    flujo_ecobici = flujo_ecobici.rename(columns={"viajes": "flujo_ecobici"})

    molinetes_hex = pd.read_parquet(FEATURES / "molinetes_estaciones_hex.parquet")[["estacion_norm", "linea_norm", "hex_id"]]
    molinetes_pax = pd.read_parquet(PROCESSED / "molinetes_agregado.parquet")
    molinetes_pax["turno"] = turno_desde_hora(molinetes_pax["hora"])
    molinetes_por_estacion_turno = molinetes_pax.groupby(
        ["estacion_norm", "linea_norm", "turno"]
    )["pasajeros"].sum().reset_index()
    flujo_molinetes = molinetes_por_estacion_turno.merge(molinetes_hex, on=["estacion_norm", "linea_norm"], how="inner")
    flujo_molinetes = flujo_molinetes.groupby(["hex_id", "turno"])["pasajeros"].sum().reset_index()
    flujo_molinetes = flujo_molinetes.rename(columns={"pasajeros": "flujo_molinetes"})

    TURNOS = ["Mañana", "Tarde", "Noche", "Madrugada"]
    base = pd.DataFrame(list(product(hex_maestra["hex_id"], TURNOS)), columns=["hex_id", "turno"])
    base = base.merge(flujo_ecobici, on=["hex_id", "turno"], how="left")
    base = base.merge(flujo_molinetes, on=["hex_id", "turno"], how="left")
    base["flujo_ecobici"] = base["flujo_ecobici"].fillna(0)
    base["flujo_molinetes"] = base["flujo_molinetes"].fillna(0)

    print(f"  flujo_ecobici: {base['flujo_ecobici'].sum():,.0f} viajes totales asignados a hex×turno")
    print(f"  flujo_molinetes: {base['flujo_molinetes'].sum():,.0f} pasajeros totales asignados a hex×turno")
    return base


def main() -> None:
    hex_maestra = pd.read_parquet(FEATURES / "hex_maestra.parquet").dropna(subset=["barrio_id"])

    print("POIs sensibles en buffer 300m...")
    pois = agregar_pois(hex_maestra)
    pois.to_parquet(FEATURES / "hex_pois.parquet", index=False)

    print("\nFlujo peatonal por hex×turno...")
    flujo = agregar_flujo(hex_maestra)
    flujo.to_parquet(FEATURES / "hex_flujo_turno.parquet", index=False)

    print("\nGuardado: hex_pois.parquet, hex_flujo_turno.parquet")


if __name__ == "__main__":
    main()
