"""
CAPA 4 (arquitectura-sige-ba.pdf, sección 7): genera los JSON/GeoJSON
livianos que consume dashboard/ (Next.js) — nunca lee los parquet
directo, todo pasa por acá para no acoplar el frontend al esquema de
Capa 0-3.

Salidas en dashboard/public/data/:
- hex_riesgo.geojson    — 401 hexágonos, un score_riesgo por turno como
                          propiedad (mananav/tarde/noche/madrugada) para
                          que el mapa cambie de turno sin refetch. Ya no lo
                          consume el tablero (trabaja sobre barrios) pero sí
                          presentacion/gen_mapas.py.
- modulo_a_k75.json     — patrullas propuestas con K=75 (escenario "mismo
                          presupuesto que las comisarías actuales").
- modulo_b_red.json     — cámaras propuestas sobre la red vial (ubicaciones
                          concretas), ordenadas por ganancia marginal.
- modulo_c.json         — ranking de accesos/controles.
- comisarias.geojson    — 75 comisarías reales (contexto en el mapa).
- camaras.geojson       — 224 cámaras reales (contexto en el mapa).

Las salidas por barrio y comuna que consume el tablero salen del otro script
de esta capa: generar_export_dashboard.py.

Se dejaron de exportar tres archivos que ya no lee nadie: `modulo_a.json`
(K=40, reemplazado por el escenario K=75), `modulo_b.json` (versión sobre
hexágonos, reemplazada por la red vial) y `metricas.json` (los paneles de
calibración y evolución del dashboard viejo). Los parquet de origen siguen
donde estaban; lo que se corta es la copia en public/data/, que se subía a
producción sin que nada la pidiera. `metricas.json` además tenía los números
de v1/v2 y de cobertura hardcodeados, o sea una segunda copia del README que
había que actualizar a mano — el problema que este proyecto ya tuvo tres veces.
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


def exportar_modulo_a_k75() -> None:
    """El escenario de 75 patrullas — el que titula el material de presentación
    ('mismo presupuesto que las 75 comisarías, 58,7% de cobertura'). El K=40 que
    se exportaba antes quedó sin consumidores; ver README, 'Escenario de
    recursos'."""
    ruta = FEATURES / "modulo_a_patrullas_Tarde_k75.parquet"
    if not ruta.exists():
        print("modulo_a_k75.json: falta el parquet — correr modulo_a_patrullas.py --k 75")
        return
    df = pd.read_parquet(ruta)
    df.to_json(OUT / "modulo_a_k75.json", orient="records", force_ascii=False)
    print(f"modulo_a_k75.json: {len(df)} ubicaciones (escenario K=75)")


def exportar_modulo_b_red() -> None:
    """Versión sobre la red vial — la que corresponde usar. Son ubicaciones
    concretas (intersecciones), no zonas de 700m. La versión sobre hexágonos
    sigue en `modulo_b_camaras.parquet` para poder comparar, pero ya no se
    exporta; ver README, 'Módulo B sobre la red vial'."""
    ruta = FEATURES / "modulo_b_camaras_red.parquet"
    if not ruta.exists():
        print("modulo_b_red.json: falta modulo_b_camaras_red.parquet — se omite")
        return
    df = pd.read_parquet(ruta)
    df.to_json(OUT / "modulo_b_red.json", orient="records", force_ascii=False)
    print(f"modulo_b_red.json: {len(df)} cámaras sobre la red vial")


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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    exportar_hex_riesgo()
    exportar_modulo_a_k75()
    exportar_modulo_b_red()
    exportar_modulo_c()

    comisarias = pd.read_parquet(PROCESSED / "comisarias_policia.parquet")
    exportar_puntos("comisarias.geojson", comisarias, ["nombre", "barrio", "comuna"])

    camaras = pd.read_parquet(PROCESSED / "camaras.parquet").rename(columns={"latitud": "lat", "longitud": "lon"})
    exportar_puntos("camaras.geojson", camaras, ["tipo_de_fiscalizador"])

    print(f"\nTodo exportado a {OUT}")


if __name__ == "__main__":
    main()
