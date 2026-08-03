"""
CAPA 2, Módulo C (arquitectura-sige-ba.pdf, sección 4.3): ranking de
accesos por autopista para ubicar controles/garitas, combinando
accidentalidad histórica (siniestros_hechos) + riesgo delictivo
(riesgo_predicho) del corredor que sale de cada acceso.

Simplificación respecto al documento: el documento pide "recorrer los
tramos troncales/distribuidores" del grafo vial desde cada acceso —
eso requiere topología real de calles (qué tramo conecta con cuál),
que no existe en calles.parquet (son geometrías sueltas, sin nodos
compartidos armados). En vez de construir esa topología, acá el
"corredor" se aproxima como los tramos de jerarquía troncal/distribuidora
principal dentro de un radio fijo del acceso (RADIO_CORREDOR_M) — capta
el mismo espíritu (¿qué vías importantes salen de este acceso y qué tan
peligrosas son?) sin el costo de armar un grafo navegable. Si el radio
resulta muy corto/largo para algún acceso puntual, es el primer lugar
para ajustar.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

PROCESSED = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"

CRS_GEO = "EPSG:4326"
CRS_METROS = "EPSG:5347"

RADIO_CORREDOR_M = 2000
JERARQUIAS_CORREDOR = ["VÍA TRONCAL", "VÍA DISTRIBUIDORA PRINCIPAL"]


def coords_metros(df: pd.DataFrame) -> np.ndarray:
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=CRS_GEO).to_crs(CRS_METROS)
    return np.array([(p.x, p.y) for p in gdf.geometry])


def main() -> None:
    accesos = pd.read_parquet(FEATURES / "accesos_autopistas_hex.parquet").dropna(subset=["lat", "lon"])
    calles = pd.read_parquet(FEATURES / "calles_hex.parquet")
    calles = calles[calles["jerarquia"].isin(JERARQUIAS_CORREDOR)].dropna(subset=["lat", "lon"])

    acc_xy = coords_metros(accesos)
    calle_xy = coords_metros(calles)
    dist = np.sqrt(((acc_xy[:, None, :] - calle_xy[None, :, :]) ** 2).sum(axis=2))  # (n_accesos, n_calles)
    en_corredor = dist <= RADIO_CORREDOR_M

    siniestros = pd.read_parquet(FEATURES / "siniestros_hechos_hex.parquet")
    siniestros_por_hex = siniestros.groupby("hex_id", observed=True).size()

    riesgo = pd.read_parquet(FEATURES / "riesgo_predicho.parquet")
    riesgo_por_hex = riesgo.groupby("hex_id", observed=True)["score_riesgo"].mean()

    filas = []
    for i, acceso in accesos.reset_index(drop=True).iterrows():
        calles_corredor = calles.iloc[np.where(en_corredor[i])[0]]
        hexes_corredor = set(calles_corredor["hex_id"].dropna())

        accidentalidad = sum(siniestros_por_hex.get(h, 0) for h in hexes_corredor)
        riesgo_delictivo = np.mean([riesgo_por_hex.get(h, 0) for h in hexes_corredor]) if hexes_corredor else 0
        n_troncal = (calles_corredor["jerarquia"] == "VÍA TRONCAL").sum()
        n_distribuidora = (calles_corredor["jerarquia"] == "VÍA DISTRIBUIDORA PRINCIPAL").sum()

        filas.append({
            "nombre": acceso["nombre"], "autopista": acceso["autopista"],
            "accidentalidad_corredor": accidentalidad, "riesgo_delictivo_corredor": riesgo_delictivo,
            "tramos_troncales": n_troncal, "tramos_distribuidores": n_distribuidora,
            "hexagonos_en_corredor": len(hexes_corredor),
        })

    resultado = pd.DataFrame(filas)
    resultado["pct_accidentalidad"] = resultado["accidentalidad_corredor"].rank(pct=True)
    resultado["pct_riesgo"] = resultado["riesgo_delictivo_corredor"].rank(pct=True)
    resultado["score_control"] = (resultado["pct_accidentalidad"] + resultado["pct_riesgo"]) / 2
    resultado = resultado.sort_values("score_control", ascending=False).reset_index(drop=True)
    resultado["ranking"] = resultado.index + 1

    print(f"Corredor: tramos {JERARQUIAS_CORREDOR} dentro de {RADIO_CORREDOR_M}m de cada acceso\n")
    print(resultado[[
        "ranking", "nombre", "autopista", "accidentalidad_corredor",
        "riesgo_delictivo_corredor", "hexagonos_en_corredor", "score_control",
    ]].to_string(index=False))

    FEATURES.mkdir(parents=True, exist_ok=True)
    resultado.to_parquet(FEATURES / "modulo_c_controles.parquet", index=False)
    print(f"\nGuardado: modulo_c_controles.parquet")


if __name__ == "__main__":
    main()
