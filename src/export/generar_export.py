"""
CAPA 4 (arquitectura-sige-ba.pdf, sección 7): genera los JSON/GeoJSON
livianos que consume dashboard/ (Next.js) — nunca lee los parquet
directo, todo pasa por acá para no acoplar el frontend al esquema de
Capa 0-3.

Salidas en dashboard/public/data/:
- hex_riesgo.geojson    — 401 hexágonos, un score_riesgo por turno como
                          propiedad (mananav/tarde/noche/madrugada) para
                          que el mapa cambie de turno sin refetch.
- modulo_a.json         — ubicaciones de patrullas propuestas (turno Tarde).
- modulo_b.json         — cámaras nuevas propuestas, ordenadas por ranking.
- modulo_c.json         — ranking de accesos/controles.
- comisarias.geojson    — 75 comisarías reales (contexto en el mapa).
- camaras.geojson       — 224 cámaras reales (contexto en el mapa).
- metricas.json         — evolución mensual, calibración, resumen v1/v2
                          y cobertura de Módulo A por K (para el panel
                          de métricas del modelo).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from shapely import wkt

PROCESSED = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
OUT = Path(__file__).resolve().parent.parent.parent / "dashboard" / "public" / "data"

TURNOS = ["Mañana", "Tarde", "Noche", "Madrugada"]
TURNO_KEY = {"Mañana": "manana", "Tarde": "tarde", "Noche": "noche", "Madrugada": "madrugada"}


def exportar_hex_riesgo() -> None:
    hex_maestra = pd.read_parquet(FEATURES / "hex_maestra.parquet").dropna(subset=["barrio_id"])
    riesgo = pd.read_parquet(FEATURES / "riesgo_predicho.parquet")
    pivot = riesgo.pivot(index="hex_id", columns="turno", values="score_riesgo")

    features = []
    for _, hex_row in hex_maestra.iterrows():
        hid = hex_row["hex_id"]
        geom = wkt.loads(hex_row["geometry_wkt"])
        scores = pivot.loc[hid] if hid in pivot.index else pd.Series(dtype=float)
        props = {
            "hex_id": hid,
            "barrio": hex_row["barrio_id"],
            "comuna": int(hex_row["comuna_id"]),
        }
        for t in TURNOS:
            props[f"riesgo_{TURNO_KEY[t]}"] = round(float(scores.get(t, 0)), 4)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [list(geom.exterior.coords)]},
            "properties": props,
        })

    geojson = {"type": "FeatureCollection", "features": features}
    (OUT / "hex_riesgo.geojson").write_text(json.dumps(geojson), encoding="utf-8")
    print(f"hex_riesgo.geojson: {len(features)} hexágonos")


def exportar_modulo_a() -> None:
    df = pd.read_parquet(FEATURES / "modulo_a_patrullas_Tarde.parquet")
    df.to_json(OUT / "modulo_a.json", orient="records", force_ascii=False)
    print(f"modulo_a.json: {len(df)} ubicaciones")


def exportar_modulo_b() -> None:
    df = pd.read_parquet(FEATURES / "modulo_b_camaras.parquet")
    df.to_json(OUT / "modulo_b.json", orient="records", force_ascii=False)
    print(f"modulo_b.json: {len(df)} cámaras propuestas")


def exportar_modulo_c() -> None:
    df = pd.read_parquet(FEATURES / "modulo_c_controles.parquet")
    df.to_json(OUT / "modulo_c.json", orient="records", force_ascii=False)
    print(f"modulo_c.json: {len(df)} accesos rankeados")


def exportar_puntos(nombre_archivo: str, df: pd.DataFrame, props_cols: list[str]) -> None:
    features = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
        "properties": {c: row[c] for c in props_cols},
    } for _, row in df.dropna(subset=["lat", "lon"]).iterrows()]
    geojson = {"type": "FeatureCollection", "features": features}
    (OUT / nombre_archivo).write_text(json.dumps(geojson, default=str), encoding="utf-8")
    print(f"{nombre_archivo}: {len(features)} puntos")


def exportar_metricas() -> None:
    evolucion = pd.read_parquet(FEATURES / "evolucion_mensual.parquet")
    calibracion = pd.read_parquet(FEATURES / "calibracion.parquet")
    shap_importancia = pd.read_parquet(FEATURES / "shap_importancia_global.parquet")

    # v1/v2 y cobertura de Módulo A no quedaron persistidos por sus scripts
    # (train_baseline.py, train_v2.py, modulo_a_patrullas.py solo imprimen) —
    # se copian acá desde los resultados ya documentados en el README. Si se
    # reentrena o se corre Módulo A con otro K, actualizar a mano los dos lados.
    # Modulo A actualizado post-grafo vial real (P1 auditoría): la cobertura
    # ya no es distancia euclidiana, es distancia de calle real (Dijkstra
    # sobre el grafo dirigido de OSM) — números bastante más bajos que la
    # versión euclidiana anterior, que estaba sobreestimada.
    metricas = {
        "v1_vs_v2": {
            "v1": {"mae": 0.2923, "recall_20": 0.455, "recall_30": 0.586},
            "v2": {"mae": 0.2906, "recall_20": 0.454, "recall_30": 0.585},
            "baseline_naive": {"mae": 0.2983, "recall_20": 0.447, "recall_30": 0.584},
        },
        "modulo_a_cobertura": {
            "actual_75_comisarias": 0.3509,
            "k20": 0.2704, "k40": 0.418, "k75": 0.5865,
        },
        "evolucion_mensual": evolucion.to_dict(orient="records"),
        "calibracion": calibracion.to_dict(orient="records"),
        "shap_importancia": shap_importancia.to_dict(orient="records"),
    }
    (OUT / "metricas.json").write_text(json.dumps(metricas, default=str), encoding="utf-8")
    print("metricas.json guardado")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    exportar_hex_riesgo()
    exportar_modulo_a()
    exportar_modulo_b()
    exportar_modulo_c()

    comisarias = pd.read_parquet(PROCESSED / "comisarias_policia.parquet")
    exportar_puntos("comisarias.geojson", comisarias, ["nombre", "barrio", "comuna"])

    camaras = pd.read_parquet(PROCESSED / "camaras.parquet").rename(columns={"latitud": "lat", "longitud": "lon"})
    exportar_puntos("camaras.geojson", camaras, ["tipo_de_fiscalizador"])

    exportar_metricas()
    print(f"\nTodo exportado a {OUT}")


if __name__ == "__main__":
    main()
