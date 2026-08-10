"""
CAPA 2, Módulo B (arquitectura-sige-ba.pdf, sección 4.2): ubicación de
cámaras nuevas como Weighted Max Coverage, resuelto greedy (no MILP como
Módulo A) — el documento pide explícitamente un "ranking de ubicaciones
candidatas ordenado por ganancia marginal de cobertura", que es
justamente lo que produce el algoritmo greedy clásico de max coverage
(cada paso elige el candidato que suma más peso nuevo).

Peso de cada hexágono de demanda = riesgo (promedio de riesgo_predicho
sobre los 4 turnos, porque una cámara mira las 24hs, no un turno) ×
boost por baja densidad de alumbrado × boost por alto flujo peatonal
(ecobici + molinetes combinados, normalizados por percentil porque las
escalas son muy distintas — millones de pasajeros de subte vs miles de
viajes de ecobici) × descuento si ya está dentro del radio de una cámara
existente (no se excluye del todo, una zona muy caliente puede justificar
más de una cámara, pero pesa menos que una zona sin ninguna).

Candidatos: los 401 centroides de hex, salvo los que caen a <100m de una
cámara ya instalada (filtro duro, pedido explícito del documento — no
tiene sentido proponer una cámara pegada a otra).

OJO — a esta resolución el max coverage degenera en un ranking
=============================================================
Los centroides H3-8 están a 700m unos de otros (mediana 701m) y
RADIO_COBERTURA_M es 150 — cada candidato cubre SOLO su propio hexágono.
La matriz `cobertura` de greedy_max_coverage() es la identidad, así que
la ganancia marginal de cada candidato es siempre su propio peso y el
greedy equivale a ordenar por peso y cortar en N. Medido: a 150m, 300m y
500m el promedio de vecinos cubiertos además de sí mismo es 0,00; recién
a 800m sube a 1,88.

Dos consecuencias que importan al reportar el resultado:

1. El porcentaje que imprime main() NO es "riesgo cubierto por las
   cámaras" — es la fracción del riesgo ponderado que vive en los N
   hexágonos más pesados. Reportarlo como cobertura sobrevende el método.
2. Migrar esto a distancia de red (como se hizo en Módulo A y C) no
   cambiaría nada: verificado, 0,00% de pares distintos y las mismas 30
   ubicaciones. Por eso quedó en distancia euclidiana.

El valor real del módulo está en la PONDERACIÓN (riesgo × oscuridad ×
flujo, con descuento por cámara cercana), que prioriza zonas donde una
cámara agrega más. La ubicación puntual dentro de la zona es decisión de
campo. Resolverlo de verdad como cobertura pediría una grilla H3-10
(centroides a ~100m), pero el riesgo se modela en H3-8: habría que
desagregar a una resolución que el modelo no tiene. Ver README.
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

N_CAMARAS_NUEVAS = 30      # presupuesto — parámetro ajustable
RADIO_COBERTURA_M = 150    # qué tanto "ve"/disuade una cámara
RADIO_EXCLUSION_M = 100    # no proponer una cámara nueva pegada a una existente
DESCUENTO_YA_CUBIERTO = 0.3  # peso remanente de un hex que ya está en radio de una cámara existente


def coords_metros(df: pd.DataFrame) -> np.ndarray:
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=CRS_GEO).to_crs(CRS_METROS)
    return np.array([(p.x, p.y) for p in gdf.geometry])


def calcular_flujo_peatonal(hex_ids: list[str]) -> pd.Series:
    ecobici_hex = pd.read_parquet(FEATURES / "ecobici_estaciones_hex.parquet")[["id_estacion", "hex_id"]]
    ecobici_viajes = pd.read_parquet(PROCESSED / "ecobici_viajes_agregado.parquet").groupby("id_estacion")["viajes"].sum()
    ecobici_hex = ecobici_hex.merge(ecobici_viajes.rename("viajes"), on="id_estacion", how="left")
    flujo_ecobici = ecobici_hex.groupby("hex_id")["viajes"].sum()

    molinetes_hex = pd.read_parquet(FEATURES / "molinetes_estaciones_hex.parquet")[["estacion_norm", "linea_norm", "hex_id"]]
    molinetes_pax = pd.read_parquet(PROCESSED / "molinetes_agregado.parquet").groupby(
        ["estacion_norm", "linea_norm"]
    )["pasajeros"].sum()
    molinetes_hex = molinetes_hex.merge(molinetes_pax.rename("pasajeros"), on=["estacion_norm", "linea_norm"], how="left")
    flujo_molinetes = molinetes_hex.groupby("hex_id")["pasajeros"].sum()

    flujo = pd.DataFrame(index=hex_ids)
    flujo["ecobici"] = flujo_ecobici.reindex(hex_ids).fillna(0)
    flujo["molinetes"] = flujo_molinetes.reindex(hex_ids).fillna(0)
    # percentil en vez de valor crudo: ecobici son miles de viajes, molinetes miles de millones de pasajeros
    pct_ecobici = flujo["ecobici"].rank(pct=True)
    pct_molinetes = flujo["molinetes"].rank(pct=True)
    return (pct_ecobici + pct_molinetes) / 2


def cargar_demanda() -> pd.DataFrame:
    riesgo = pd.read_parquet(FEATURES / "riesgo_predicho.parquet")
    riesgo_diario = riesgo.groupby("hex_id", observed=True)["score_riesgo"].mean().rename("riesgo")

    hex_maestra = pd.read_parquet(FEATURES / "hex_maestra.parquet").dropna(subset=["barrio_id"])
    hex_ids = hex_maestra["hex_id"].tolist()

    alumbrado = pd.read_parquet(FEATURES / "alumbrado_hex.parquet")["hex_id"].value_counts()
    n_luminarias = alumbrado.reindex(hex_ids).fillna(0)
    pct_alumbrado = n_luminarias.rank(pct=True)  # 1.0 = más iluminado

    flujo_pct = calcular_flujo_peatonal(hex_ids)

    demanda = hex_maestra[["hex_id", "lat", "lon"]].copy()
    demanda["riesgo"] = demanda["hex_id"].map(riesgo_diario).fillna(0)
    demanda["boost_alumbrado"] = 1 + (1 - demanda["hex_id"].map(pct_alumbrado).fillna(0.5))
    demanda["boost_flujo"] = 1 + demanda["hex_id"].map(flujo_pct).fillna(0)
    demanda["peso"] = demanda["riesgo"] * demanda["boost_alumbrado"] * demanda["boost_flujo"]
    return demanda.reset_index(drop=True)


def aplicar_descuento_y_filtro(demanda: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    camaras = pd.read_parquet(PROCESSED / "camaras.parquet").dropna(subset=["latitud", "longitud"])
    camaras = camaras.rename(columns={"latitud": "lat", "longitud": "lon"})

    dem_xy = coords_metros(demanda)
    cam_xy = coords_metros(camaras)
    dist = np.sqrt(((dem_xy[:, None, :] - cam_xy[None, :, :]) ** 2).sum(axis=2))  # (n_hex, n_camaras)

    ya_cubierto = (dist <= RADIO_COBERTURA_M).any(axis=1)
    demanda = demanda.copy()
    demanda.loc[ya_cubierto, "peso"] *= DESCUENTO_YA_CUBIERTO

    demasiado_cerca = (dist <= RADIO_EXCLUSION_M).any(axis=1)
    print(f"Hexágonos descontados por cámara cercana (<{RADIO_COBERTURA_M}m): {ya_cubierto.sum()}")
    print(f"Hexágonos excluidos como candidatos (<{RADIO_EXCLUSION_M}m de una cámara): {demasiado_cerca.sum()}")
    return demanda, demasiado_cerca


def greedy_max_coverage(demanda: pd.DataFrame, excluidos: np.ndarray, n: int) -> pd.DataFrame:
    xy = coords_metros(demanda)
    dist_candidato_demanda = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(axis=2))
    cobertura = dist_candidato_demanda <= RADIO_COBERTURA_M  # (n_candidatos, n_demanda), candidatos = mismos hex

    peso = demanda["peso"].to_numpy()
    candidatos_disponibles = set(np.where(~excluidos)[0])
    cubierto = np.zeros(len(demanda), dtype=bool)

    elegidos = []
    for _ in range(n):
        mejor_j, mejor_ganancia = None, -1.0
        for j in candidatos_disponibles:
            nuevos = cobertura[j] & ~cubierto
            ganancia = peso[nuevos].sum()
            if ganancia > mejor_ganancia:
                mejor_j, mejor_ganancia = j, ganancia
        if mejor_j is None or mejor_ganancia <= 0:
            break
        cubierto |= cobertura[mejor_j]
        candidatos_disponibles.remove(mejor_j)
        elegidos.append((mejor_j, mejor_ganancia))

    filas = []
    for rank, (j, ganancia) in enumerate(elegidos, start=1):
        filas.append({
            "ranking": rank, "hex_id": demanda["hex_id"].iloc[j],
            "lat": demanda["lat"].iloc[j], "lon": demanda["lon"].iloc[j],
            "ganancia_marginal": ganancia,
        })
    return pd.DataFrame(filas)


def main() -> None:
    demanda = cargar_demanda()
    demanda, excluidos = aplicar_descuento_y_filtro(demanda)

    peso_total = demanda["peso"].sum()
    resultado = greedy_max_coverage(demanda, excluidos, N_CAMARAS_NUEVAS)
    cobertura_lograda = resultado["ganancia_marginal"].sum() / peso_total

    # "concentran", no "cubren": a 150m sobre grilla H3-8 cada candidato solo
    # cubre su propio hexágono (ver docstring del módulo) — el número es la
    # fracción del riesgo ponderado que vive en esas N zonas, no cobertura.
    print(f"\n{len(resultado)} zonas priorizadas, concentran {cobertura_lograda:.1%} del riesgo ponderado total")
    print(resultado[["ranking", "hex_id", "ganancia_marginal"]].head(10))

    FEATURES.mkdir(parents=True, exist_ok=True)
    resultado.to_parquet(FEATURES / "modulo_b_camaras.parquet", index=False)
    print(f"\nGuardado: modulo_b_camaras.parquet")


if __name__ == "__main__":
    main()
