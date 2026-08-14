"""
CAPA 4 — las salidas que consume el dashboard nuevo, aparte de las que ya genera
`generar_export.py`.

El dashboard viejo dibujaba la grilla H3 cruda. El nuevo trabaja sobre unidades
que una persona reconoce —barrio y comuna— y necesita además las series y curvas
que hoy solo existen como parquet o como prosa en el README.

Salidas en dashboard/public/data/:

- barrios_riesgo.geojson   48 polígonos con riesgo por turno (promedio de sus
                           hexágonos, que es lo comparable entre barrios de
                           distinto tamaño), riesgo total, delitos 2025 y
                           cantidad de hexágonos.
- comunas_resumen.json     lo mismo agregado a las 15 comunas, para los filtros
                           y la tabla de detalle.
- curva_k.json             cobertura del Módulo A para cada K — lo que hace que
                           el control de patrullas del tablero sea real y no una
                           interpolación.
- sensibilidad_radio.json  el barrido de radio, para poder mostrar de qué
                           depende el número.
- serie_delitos.json       serie mensual por tipo, 2016-2025, para las
                           tendencias y el contexto del quiebre de 2025.
- resumen.json             los números sueltos que van en las tarjetas de KPI,
                           en un solo lugar en vez de hardcodeados en el front.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from shapely import wkt
from shapely.geometry import mapping

RAIZ = Path(__file__).resolve().parent.parent.parent
PROCESSED = RAIZ / "data" / "processed"
FEATURES = RAIZ / "data" / "features"
OUT = RAIZ / "dashboard" / "public" / "data"

TURNOS = ["Mañana", "Tarde", "Noche", "Madrugada"]
TURNO_KEY = {"Mañana": "manana", "Tarde": "tarde", "Noche": "noche", "Madrugada": "madrugada"}
ANIO_ULTIMO = 2025


def _riesgo_por_hex() -> pd.DataFrame:
    """hex_id × turno -> score, más el barrio y la comuna de cada hexágono."""
    riesgo = pd.read_parquet(FEATURES / "riesgo_predicho.parquet")
    pivot = riesgo.pivot(index="hex_id", columns="turno", values="score_riesgo")
    # `turno` viene como categórica y un índice de columnas categórico rompe el
    # merge de abajo (InvalidIndexError); se aplana a strings comunes
    pivot.columns = [str(c) for c in pivot.columns]
    pivot.index = pivot.index.astype(str)
    hexes = (pd.read_parquet(FEATURES / "hex_maestra.parquet")
             .dropna(subset=["barrio_id"])[["hex_id", "barrio_id", "comuna_id"]])
    hexes["hex_id"] = hexes["hex_id"].astype(str)
    hexes["barrio_id"] = hexes["barrio_id"].astype(str)
    return hexes.merge(pivot, left_on="hex_id", right_index=True, how="left").fillna(0)


# Único desajuste de nombres entre el polígono y el campo `barrio` de delitos.
# Es el mismo caso que ya estaba documentado para el dataset de población: el
# polígono dice "La Boca" y las otras fuentes dicen "BOCA". Se resuelve con un
# alias explícito en vez de un fuzzy match, que sobre 48 nombres es riesgo puro.
ALIAS_BARRIO = {"LA BOCA": "BOCA"}

_DELITOS: pd.DataFrame | None = None


def delitos() -> pd.DataFrame:
    """Carga delitos_hex UNA sola vez y la deja en dtypes chicos.

    Cada exportador necesita una vista distinta de la misma tabla, y releerla
    por función tiraba ArrayMemoryError en esta máquina de 3,4GB: 1,35M filas de
    datetime64 son 10MB por copia, y el filtro por año hace un take() que
    duplica. Se convierte la fecha a año/mes enteros y se descartan las columnas
    de texto a categóricas, que es lo que se consulta después.
    """
    global _DELITOS
    if _DELITOS is None:
        d = pd.read_parquet(FEATURES / "delitos_hex.parquet",
                            columns=["fecha", "barrio", "comuna", "tipo"])
        f = pd.to_datetime(d["fecha"], errors="coerce")
        _DELITOS = pd.DataFrame({
            "anio": f.dt.year.astype("int16"),
            "mes": f.dt.month.astype("int8"),
            "barrio": d["barrio"].astype(str).str.upper().str.strip().astype("category"),
            "comuna": pd.to_numeric(d["comuna"], errors="coerce"),
            "tipo": d["tipo"].astype("category"),
        })
        del d, f
    return _DELITOS


def _delitos_por_barrio() -> pd.Series:
    d = delitos()
    return d.loc[d["anio"] == ANIO_ULTIMO, "barrio"].value_counts()


def _delitos_de(nombre: str, conteo: pd.Series) -> int:
    clave = ALIAS_BARRIO.get(nombre.upper(), nombre.upper())
    return int(conteo.get(clave, 0))


def exportar_barrios() -> None:
    barrios = pd.read_parquet(PROCESSED / "barrios.parquet")
    por_hex = _riesgo_por_hex()
    por_barrio = _delitos_por_barrio()   # ojo: no llamarlo `delitos`, tapa a la función

    # promedio por hexágono, no suma: los barrios varían mucho en superficie y
    # sumar convierte el mapa en un mapa de tamaños. El total se guarda aparte
    # porque para asignar recursos sí importa el volumen.
    agg = por_hex.groupby("barrio_id").agg(
        n_hex=("hex_id", "size"), comuna=("comuna_id", "first"),
        **{f"m_{t}": (t, "mean") for t in TURNOS if t in por_hex.columns},
        **{f"s_{t}": (t, "sum") for t in TURNOS if t in por_hex.columns},
    )

    features = []
    for _, b in barrios.iterrows():
        nombre = str(b["nombre"]).strip()
        fila = agg.loc[nombre] if nombre in agg.index else None
        props = {
            "nombre": nombre,
            "comuna": int(fila["comuna"]) if fila is not None else None,
            "n_hex": int(fila["n_hex"]) if fila is not None else 0,
            "delitos_2025": _delitos_de(nombre, por_barrio),
        }
        for t in TURNOS:
            k = TURNO_KEY[t]
            props[f"riesgo_{k}"] = round(float(fila[f"m_{t}"]), 5) if fila is not None else 0.0
            props[f"riesgo_total_{k}"] = round(float(fila[f"s_{t}"]), 4) if fila is not None else 0.0
        # los polígonos del portal traen muchísimos vértices (716KB para 48
        # barrios); 5e-5 grados son ~5m, invisible a escala de ciudad y baja el
        # archivo a un cuarto. preserve_topology evita que se rompan los bordes
        # compartidos entre barrios vecinos.
        geom = wkt.loads(b["geometry_wkt"]).simplify(5e-5, preserve_topology=True)
        features.append({"type": "Feature", "properties": props,
                         "geometry": mapping(geom)})

    (OUT / "barrios_riesgo.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    print(f"barrios_riesgo.geojson: {len(features)} barrios")


def exportar_comunas() -> None:
    por_hex = _riesgo_por_hex()
    d = delitos()
    por_comuna = (d.loc[(d["anio"] == ANIO_ULTIMO) & d["comuna"].notna(), "comuna"]
                  .astype(int).value_counts())

    filas = []
    for comuna, g in por_hex.groupby("comuna_id"):
        fila = {"comuna": int(comuna), "n_hex": int(len(g)),
                "n_barrios": int(g["barrio_id"].nunique()),
                "delitos_2025": int(por_comuna.get(int(comuna), 0))}
        for t in TURNOS:
            if t in g.columns:
                fila[f"riesgo_{TURNO_KEY[t]}"] = round(float(g[t].mean()), 5)
        filas.append(fila)
    (OUT / "comunas_resumen.json").write_text(
        json.dumps(filas, ensure_ascii=False), encoding="utf-8")
    print(f"comunas_resumen.json: {len(filas)} comunas")


def copiar_json(origen: Path, destino: str) -> None:
    if not origen.exists():
        print(f"{destino}: falta {origen.name} — se omite")
        return
    (OUT / destino).write_text(origen.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"{destino}: copiado")


def exportar_serie_delitos() -> None:
    serie = (delitos().groupby(["anio", "mes", "tipo"], observed=True)
             .size().rename("n").reset_index())
    (OUT / "serie_delitos.json").write_text(
        serie.to_json(orient="records", force_ascii=False), encoding="utf-8")
    print(f"serie_delitos.json: {len(serie)} filas ({serie.anio.min()}-{serie.anio.max()})")


def exportar_resumen() -> None:
    """Los números de las tarjetas de KPI. Van acá y no hardcodeados en el
    front, para que haya un solo lugar donde corregirlos — el proyecto ya tuvo
    tres veces el problema de tablas desactualizadas en el README."""
    curva = json.loads((FEATURES / "modulo_a_curva_k.json").read_text(encoding="utf-8"))
    por_anio = delitos()["anio"].value_counts().sort_index()

    resumen = {
        "periodo": {"desde": int(por_anio.index.min()), "hasta": int(por_anio.index.max())},
        "delitos_ultimo_anio": int(por_anio.loc[ANIO_ULTIMO]),
        "delitos_anio_previo": int(por_anio.loc[ANIO_ULTIMO - 1]),
        "n_hexagonos": 401,
        "n_barrios": 48,
        "n_comunas": 15,
        "modelo": {
            "mae": 0.2902, "mae_naive": 0.2961,
            "recall_20": 0.454, "recall_20_naive": 0.4467,
            "pai_10": 2.77, "pei_10": 0.995,
            "concentracion_30pct_area": 0.585,
        },
        "modulo_a": {
            "cobertura_actual": curva["cobertura_actual"],
            "n_comisarias": curva["n_comisarias"],
            "radio_m": curva["radio_m"],
            "turno": curva["turno"],
        },
        "modulo_b": {"n_camaras_existentes": 224, "cobertura_30_camaras": 0.0703,
                     "km_cubiertos_30": 86.4, "km_red": 3927},
        "modulo_c": {"n_corredores": 9, "primero": "Pórtico Independencia",
                     "siniestros_km_primero": 53.7},
        "salvedades": [
            "El nivel de delitos de 2025 no es confiable: robo y hurto caen de golpe y de forma uniforme, "
            "el hurto automotor no se mueve, y las encuestas de victimización no acompañan. "
            "El ranking espacial sí aguanta (Spearman 0,9989 al reponderar).",
            "El modelo le gana al promedio histórico apenas 2% en error. Lo que hace bien es concentrar: "
            "el 30% del área reúne el 58,5% de los delitos.",
            "Las ubicaciones del Módulo A dependen del radio de cobertura: con 1.000 m en vez de 800, "
            "solo el 28% de las posiciones coincide. El tamaño de la ganancia sí es robusto.",
            "Cobertura no es delito evitado. Medirlo requiere un piloto con zonas de control.",
        ],
    }
    (OUT / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    print("resumen.json: guardado")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    exportar_barrios()
    exportar_comunas()
    copiar_json(FEATURES / "modulo_a_curva_k.json", "curva_k.json")
    copiar_json(FEATURES / "sensibilidad_radio_patrullas.json", "sensibilidad_radio.json")
    exportar_serie_delitos()
    exportar_resumen()
    print(f"\nTodo en {OUT}")


if __name__ == "__main__":
    main()
