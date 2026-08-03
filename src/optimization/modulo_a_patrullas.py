"""
CAPA 2, Módulo A (arquitectura-sige-ba.pdf, sección 4.1): asignación de
patrullas como Maximal Covering Location Problem (MCLP) — no es un
modelo de ML, es programación lineal entera (pulp), resuelto sobre el
output de Capa 1 (riesgo_predicho.parquet).

Formulación estándar de MCLP:
  maximizar   Σ riesgo_i * x_i
  sujeto a    Σ y_j <= K                          (presupuesto de K patrullas)
              x_i <= Σ_{j cubre i} y_j             (i solo cuenta como cubierto
                                                     si hay una patrulla a <= R)
              Σ_{i en comuna c} x_i >= 1  ∀c        (piso: ninguna comuna
                                                     entera queda sin cobertura)
              x_i, y_j ∈ {0,1}

Candidatos (dónde puede ir una patrulla): las 75 comisarías reales
(comisarias_policia.parquet) + los 401 centroides de hex_maestra — el
documento pide "comisarías actuales como puntos candidatos base +
hexágonos de alto riesgo como candidatos adicionales"; acá se usan todos
los hexágonos válidos como candidatos, no solo los de alto riesgo, para
no sesgar la solución de antemano.

Baseline de comparación ("la distribución actual", sección 4.1): cobertura
lograda hoy usando las 75 comisarías reales tal cual están, mismo radio R.
No se compara contra K=75 optimizado — la pregunta que importa es "con K
patrullas puestas donde más rinden, ¿cuánto riesgo cubro vs. lo que ya
cubre la infraestructura fija de comisarías?", no "¿y si moviera las 75
comisarías?".
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pulp

PROCESSED = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"

CRS_GEO = "EPSG:4326"
CRS_METROS = "EPSG:5347"

TURNO = "Tarde"          # turno a optimizar — el de mayor riesgo promedio (ver predecir_riesgo.py)
K_PATRULLAS = 40         # presupuesto de móviles — parámetro ajustable ("slider del dashboard")
RADIO_COBERTURA_M = 800  # cobertura efectiva de una patrulla en zona urbana densa (sección 4.1)


def cargar_demanda() -> pd.DataFrame:
    riesgo = pd.read_parquet(FEATURES / "riesgo_predicho.parquet")
    demanda = riesgo[riesgo["turno"] == TURNO].copy().reset_index(drop=True)
    return demanda


def cargar_candidatos(demanda: pd.DataFrame) -> pd.DataFrame:
    comisarias = pd.read_parquet(PROCESSED / "comisarias_policia.parquet")[["id", "nombre", "lat", "lon", "comuna"]]
    comisarias["tipo"] = "comisaría existente"
    comisarias["candidato_id"] = "com_" + comisarias["id"].astype(str)

    hexes = demanda[["hex_id", "lat", "lon", "comuna_id"]].rename(columns={"comuna_id": "comuna", "hex_id": "id"})
    hexes["nombre"] = "hex " + hexes["id"].astype(str)
    hexes["tipo"] = "hexágono candidato"
    hexes["candidato_id"] = "hex_" + hexes["id"].astype(str)

    candidatos = pd.concat([
        comisarias[["candidato_id", "nombre", "lat", "lon", "comuna", "tipo"]],
        hexes[["candidato_id", "nombre", "lat", "lon", "comuna", "tipo"]],
    ], ignore_index=True)
    return candidatos


def matriz_cobertura(demanda: pd.DataFrame, candidatos: pd.DataFrame) -> np.ndarray:
    dem_gdf = gpd.GeoDataFrame(demanda, geometry=gpd.points_from_xy(demanda["lon"], demanda["lat"]), crs=CRS_GEO).to_crs(CRS_METROS)
    can_gdf = gpd.GeoDataFrame(candidatos, geometry=gpd.points_from_xy(candidatos["lon"], candidatos["lat"]), crs=CRS_GEO).to_crs(CRS_METROS)

    dem_xy = np.array([(p.x, p.y) for p in dem_gdf.geometry])
    can_xy = np.array([(p.x, p.y) for p in can_gdf.geometry])
    dist = np.sqrt(((dem_xy[:, None, :] - can_xy[None, :, :]) ** 2).sum(axis=2))
    return dist <= RADIO_COBERTURA_M


def resolver_mclp(demanda: pd.DataFrame, candidatos: pd.DataFrame, cobertura: np.ndarray, k: int) -> list[int]:
    n_dem, n_can = cobertura.shape
    prob = pulp.LpProblem("patrullas_mclp", pulp.LpMaximize)

    y = [pulp.LpVariable(f"y_{j}", cat="Binary") for j in range(n_can)]
    x = [pulp.LpVariable(f"x_{i}", cat="Binary") for i in range(n_dem)]

    prob += pulp.lpSum(demanda["score_riesgo"].iloc[i] * x[i] for i in range(n_dem))
    prob += pulp.lpSum(y) <= k

    for i in range(n_dem):
        candidatos_que_cubren = np.where(cobertura[i])[0]
        if len(candidatos_que_cubren) == 0:
            prob += x[i] == 0  # ningún candidato a <= R — no se puede cubrir, no forzar infactibilidad
        else:
            prob += x[i] <= pulp.lpSum(y[j] for j in candidatos_que_cubren)

    for comuna, grupo in demanda.groupby("comuna_id"):
        idxs = grupo.index.tolist()
        if any(len(np.where(cobertura[i])[0]) > 0 for i in idxs):
            prob += pulp.lpSum(x[i] for i in idxs) >= 1

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    print(f"Estado del solver: {pulp.LpStatus[prob.status]}")

    elegidos = [j for j in range(n_can) if y[j].value() == 1]
    return elegidos


def cobertura_lograda(demanda: pd.DataFrame, cobertura: np.ndarray, indices_activos: list[int]) -> float:
    if not indices_activos:
        return 0.0
    cubierto = cobertura[:, indices_activos].any(axis=1)
    return demanda.loc[cubierto, "score_riesgo"].sum() / demanda["score_riesgo"].sum()


def main() -> None:
    demanda = cargar_demanda()
    candidatos = cargar_candidatos(demanda)
    print(f"Demanda: {len(demanda)} hexágonos (turno {TURNO}) | Candidatos: {len(candidatos)} "
          f"({(candidatos['tipo'] == 'comisaría existente').sum()} comisarías + "
          f"{(candidatos['tipo'] == 'hexágono candidato').sum()} hexágonos)")

    cobertura = matriz_cobertura(demanda, candidatos)

    idx_comisarias_actuales = candidatos.index[candidatos["tipo"] == "comisaría existente"].tolist()
    pct_actual = cobertura_lograda(demanda, cobertura, idx_comisarias_actuales)
    print(f"\nCobertura ACTUAL (75 comisarías reales, R={RADIO_COBERTURA_M}m): {pct_actual:.1%} del riesgo total")

    elegidos = resolver_mclp(demanda, candidatos, cobertura, K_PATRULLAS)
    pct_optimo = cobertura_lograda(demanda, cobertura, elegidos)
    print(f"Cobertura OPTIMIZADA (K={K_PATRULLAS} patrullas, R={RADIO_COBERTURA_M}m): {pct_optimo:.1%} del riesgo total")
    print(f"\nGanancia: {pct_optimo - pct_actual:+.1%} puntos de riesgo cubierto con {K_PATRULLAS} unidades "
          f"vs. {len(idx_comisarias_actuales)} comisarías fijas")

    resultado = candidatos.iloc[elegidos][["candidato_id", "nombre", "tipo", "comuna", "lat", "lon"]].reset_index(drop=True)
    print(f"\n{len(resultado)} ubicaciones elegidas ({(resultado['tipo'] == 'comisaría existente').sum()} "
          f"reutilizan comisaría existente, {(resultado['tipo'] == 'hexágono candidato').sum()} son puestos nuevos):")
    print(resultado["tipo"].value_counts())

    FEATURES.mkdir(parents=True, exist_ok=True)
    resultado.to_parquet(FEATURES / f"modulo_a_patrullas_{TURNO}.parquet", index=False)
    print(f"\nGuardado: modulo_a_patrullas_{TURNO}.parquet")


if __name__ == "__main__":
    main()
