"""
CAPA 1 (arquitectura-sige-ba.pdf, sección 3): arma la tabla de
entrenamiento del modelo núcleo, grano (hex_id, fecha, turno).

v1 (sección 8, paso 2 del roadmap): solo históricas + vecindad espacial +
socioeconómicas + infraestructura estática + calendario. Sin exógenas
(clima/eventos/estadios) todavía — eso es v2.

Target: conteo de delitos (todos los tipos juntos). El documento pide
"por tipo_delito agrupado" pero eso multiplica la tabla por ~6 tipos
(≈35M filas) — para v1, y dada la máquina de 3.4GB de RAM del proyecto,
se arranca con el total agregado; desagregar por tipo es la extensión
natural de v2 una vez que el pipeline esté validado.

Nota sobre "vecindad espacial": el documento pide "conteo de delitos en
hexágonos vecinos" pero usar el conteo del vecino en el MISMO
(fecha,turno) que se está prediciendo sería fuga de información (en el
momento de predecir, ese dato todavía no existe). Acá se usa el conteo
de los vecinos de los últimos 30 días (su propio roll_30d, ya rezagado)
en vez del conteo contemporáneo — mismo espíritu ("contagio espacial
reciente"), sin filtrar el futuro.

Nota sobre NBI/hacinamiento: el documento dice que ambos salen de
radios_censales, pero ese dataset solo tiene NBI por radio (fino).
Hacinamiento solo existe a nivel comuna (socioeconomico_comuna.parquet)
— se suma igual, a resolución más gruesa.

Actualización: población, % espacio verde y comisaría de patrullaje por
hex ya no se aproximan por radio/centroide — salen de los overlays de
polígono reales de src/etl/overlay_poligonos.py (población prorrateada
por área, no la del radio completo).
"""

from __future__ import annotations

from pathlib import Path

import h3
import numpy as np
import pandas as pd
import requests

PROCESSED = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"

FECHA_INICIO = "2016-01-01"
FECHA_FIN = "2025-12-31"
TURNOS = ["Mañana", "Tarde", "Noche", "Madrugada"]
ANIOS_FERIADOS = range(2016, 2027)


def cargar_hexes_validos() -> pd.DataFrame:
    hex_maestra = pd.read_parquet(FEATURES / "hex_maestra.parquet")
    hexes = hex_maestra.dropna(subset=["barrio_id"]).copy()
    hexes["comuna_id"] = hexes["comuna_id"].astype(int)
    print(f"Hexágonos válidos (con barrio asignado): {len(hexes)}")
    return hexes[["hex_id", "comuna_id", "radio_censal_id"]]


def armar_grilla_densa(hex_ids: list[str]) -> pd.DataFrame:
    fechas = pd.date_range(FECHA_INICIO, FECHA_FIN, freq="D")
    idx = pd.MultiIndex.from_product([hex_ids, fechas, TURNOS], names=["hex_id", "fecha", "turno"])
    grilla = idx.to_frame(index=False)
    grilla["hex_id"] = grilla["hex_id"].astype("category")
    grilla["turno"] = grilla["turno"].astype("category")
    print(f"Grilla densa: {len(grilla):,} filas ({len(hex_ids)} hex × {len(fechas)} días × {len(TURNOS)} turnos)")
    return grilla


def cargar_conteo_delitos() -> pd.DataFrame:
    df = pd.read_parquet(FEATURES / "delitos_hex.parquet", columns=["hex_id", "fecha", "turno"])
    conteo = df.groupby(["hex_id", "fecha", "turno"], observed=True).size().reset_index(name="conteo_delitos")
    conteo["conteo_delitos"] = conteo["conteo_delitos"].astype("int16")
    return conteo


def agregar_lags_y_rolling(tabla: pd.DataFrame) -> pd.DataFrame:
    tabla = tabla.sort_values(["hex_id", "turno", "fecha"])
    g = tabla.groupby(["hex_id", "turno"], observed=True)["conteo_delitos"]

    tabla["lag_7d"] = g.shift(7)
    tabla["lag_30d"] = g.shift(30)
    tabla["lag_365d"] = g.shift(365)
    # suma de los 7/30 días previos, SIN incluir el día actual (shift(1) antes de rolling)
    tabla["roll_7d_sum"] = g.transform(lambda s: s.shift(1).rolling(7, min_periods=1).sum())
    tabla["roll_30d_sum"] = g.transform(lambda s: s.shift(1).rolling(30, min_periods=1).sum())
    return tabla


def agregar_vecindad_espacial(tabla: pd.DataFrame, hex_ids: list[str]) -> pd.DataFrame:
    hex_set = set(hex_ids)
    idx_de_hex = {h: i for i, h in enumerate(hex_ids)}
    n = len(hex_ids)

    adj_k1 = np.zeros((n, n), dtype="float32")
    adj_k2 = np.zeros((n, n), dtype="float32")
    for h in hex_ids:
        i = idx_de_hex[h]
        anillo_k1 = (set(h3.grid_disk(h, 1)) - {h}) & hex_set
        anillo_k2 = (set(h3.grid_disk(h, 2)) - set(h3.grid_disk(h, 1))) & hex_set
        for v in anillo_k1:
            adj_k1[i, idx_de_hex[v]] = 1
        for v in anillo_k2:
            adj_k2[i, idx_de_hex[v]] = 1

    # se agregan los vecinos del roll_30d propio (ya rezagado), no del conteo
    # contemporáneo, para no filtrar información futura — ver docstring del módulo.
    pivot = tabla.pivot_table(index=["fecha", "turno"], columns="hex_id", values="roll_30d_sum", observed=True)
    pivot = pivot.reindex(columns=hex_ids, fill_value=0).fillna(0)
    mat = pivot.to_numpy(dtype="float32")

    vecino_k1 = mat @ adj_k1.T
    vecino_k2 = mat @ adj_k2.T

    vecino_k1_df = pd.DataFrame(vecino_k1, index=pivot.index, columns=hex_ids).stack().rename("vecino_k1_roll30")
    vecino_k2_df = pd.DataFrame(vecino_k2, index=pivot.index, columns=hex_ids).stack().rename("vecino_k2_roll30")
    vecinos = pd.concat([vecino_k1_df, vecino_k2_df], axis=1).reset_index()
    vecinos = vecinos.rename(columns={"level_2": "hex_id"})

    tabla = tabla.merge(vecinos, on=["fecha", "turno", "hex_id"], how="left")
    return tabla


def agregar_socioeconomico_e_infraestructura(tabla: pd.DataFrame, hexes: pd.DataFrame) -> pd.DataFrame:
    radios = pd.read_parquet(PROCESSED / "radios_censales.parquet")[["id_radio", "pct_hogares_nbi"]]
    hexes = hexes.merge(radios, left_on="radio_censal_id", right_on="id_radio", how="left").drop(columns="id_radio")

    comuna_socio = pd.read_parquet(PROCESSED / "socioeconomico_comuna.parquet")
    comuna_socio = comuna_socio.rename(columns={"comuna": "comuna_id"})[
        ["comuna_id", "pct_hacinamiento_critico"]
    ]
    hexes = hexes.merge(comuna_socio, on="comuna_id", how="left")

    # población prorrateada por área (src/etl/overlay_poligonos.py) en vez de
    # la población del radio censal completo — más precisa a nivel hex.
    poblacion = pd.read_parquet(FEATURES / "hex_poblacion.parquet")
    hexes = hexes.merge(poblacion, on="hex_id", how="left")

    espacio_verde = pd.read_parquet(FEATURES / "hex_espacios_verdes.parquet")
    hexes = hexes.merge(espacio_verde, on="hex_id", how="left")

    comisaria = pd.read_parquet(FEATURES / "hex_comisaria_patrullaje.parquet")[["hex_id", "comisaria_id"]]
    hexes = hexes.merge(comisaria, on="hex_id", how="left")

    camaras = pd.read_parquet(FEATURES / "camaras_hex.parquet")["hex_id"].value_counts().rename("n_camaras")
    alumbrado = pd.read_parquet(FEATURES / "alumbrado_hex.parquet")["hex_id"].value_counts().rename("n_luminarias")
    hexes = hexes.merge(camaras, left_on="hex_id", right_index=True, how="left")
    hexes = hexes.merge(alumbrado, left_on="hex_id", right_index=True, how="left")
    hexes["n_camaras"] = hexes["n_camaras"].fillna(0)
    hexes["n_luminarias"] = hexes["n_luminarias"].fillna(0)

    tabla = tabla.merge(hexes, on="hex_id", how="left")
    return tabla


def agregar_calendario(tabla: pd.DataFrame) -> pd.DataFrame:
    tabla["dia_semana"] = tabla["fecha"].dt.dayofweek.astype("int8")
    tabla["mes"] = tabla["fecha"].dt.month.astype("int8")

    feriados = set()
    for anio in ANIOS_FERIADOS:
        resp = requests.get(f"https://api.argentinadatos.com/v1/feriados/{anio}", timeout=30)
        if resp.ok:
            feriados |= {f["fecha"] for f in resp.json()}
    tabla["es_feriado"] = tabla["fecha"].dt.strftime("%Y-%m-%d").isin(feriados)
    print(f"Feriados cargados: {len(feriados)} (2016-2026)")
    return tabla


def main() -> None:
    hexes = cargar_hexes_validos()
    hex_ids = sorted(hexes["hex_id"].tolist())

    tabla = armar_grilla_densa(hex_ids)

    conteo = cargar_conteo_delitos()
    tabla = tabla.merge(conteo, on=["hex_id", "fecha", "turno"], how="left")
    tabla["conteo_delitos"] = tabla["conteo_delitos"].fillna(0).astype("int16")

    print("Calculando lags/rolling...")
    tabla = agregar_lags_y_rolling(tabla)

    print("Calculando vecindad espacial (k=1, k=2)...")
    tabla = agregar_vecindad_espacial(tabla, hex_ids)

    print("Agregando socioeconómico e infraestructura...")
    tabla = agregar_socioeconomico_e_infraestructura(tabla, hexes)

    print("Agregando calendario...")
    tabla = agregar_calendario(tabla)

    FEATURES.mkdir(parents=True, exist_ok=True)
    tabla.to_parquet(FEATURES / "training_table.parquet", index=False)
    print(f"\nGuardado: training_table.parquet, {len(tabla):,} filas, {tabla.memory_usage(deep=True).sum() / 1e6:.0f} MB en memoria")
    print(tabla.dtypes)
    print(f"\nconteo_delitos: media={tabla['conteo_delitos'].mean():.3f}, "
          f"% ceros={(tabla['conteo_delitos'] == 0).mean():.1%}")


if __name__ == "__main__":
    main()
