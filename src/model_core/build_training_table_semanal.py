"""
Variante semanal de Capa 1: mismo modelo núcleo pero grano (hex_id,
semana, turno) en vez de (hex_id, fecha, turno). Hipótesis a probar: el
conteo diario por hex es muy disperso (82,8% de celdas en cero, media
0,23) — a esa escala un promedio histórico ya explica casi todo (ver
README, sección Capa 1 v1). Agregar por semana (~7x menos dispersión)
podría dejar ver señal dinámica que hoy queda enterrada en el ruido.

Mismas features que build_training_table.py, reescaladas a semanas:
lag 1/4/52 semanas (en vez de 7/30/365 días), roll 4/12 semanas (en vez
de 7/30 días), vecindad espacial sobre el roll_4 ya rezagado (mismo
argumento anti-fuga-de-datos que la versión diaria). "día de la semana"
no aplica a grano semanal — se cambia por semana_del_año.

No se repite el año-por-año de descarga: reusa delitos_hex.parquet y los
overlays ya calculados, esto es una resample, no una reingesta.
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
    return hexes[["hex_id", "comuna_id", "radio_censal_id"]]


def semana_de(fecha: pd.Series) -> pd.Series:
    """Lunes de la semana ISO de cada fecha."""
    return (fecha - pd.to_timedelta(fecha.dt.weekday, unit="D")).dt.normalize()


def armar_grilla_densa(hex_ids: list[str]) -> pd.DataFrame:
    semanas = pd.date_range(semana_de(pd.Series([pd.Timestamp(FECHA_INICIO)]))[0],
                             semana_de(pd.Series([pd.Timestamp(FECHA_FIN)]))[0], freq="7D")
    idx = pd.MultiIndex.from_product([hex_ids, semanas, TURNOS], names=["hex_id", "semana", "turno"])
    grilla = idx.to_frame(index=False)
    grilla["hex_id"] = grilla["hex_id"].astype("category")
    grilla["turno"] = grilla["turno"].astype("category")
    print(f"Grilla densa semanal: {len(grilla):,} filas ({len(hex_ids)} hex × {len(semanas)} semanas × {len(TURNOS)} turnos)")
    return grilla


def cargar_conteo_semanal() -> pd.DataFrame:
    df = pd.read_parquet(FEATURES / "delitos_hex.parquet", columns=["hex_id", "fecha", "turno"])
    df["semana"] = semana_de(df["fecha"])
    conteo = df.groupby(["hex_id", "semana", "turno"], observed=True).size().reset_index(name="conteo_delitos")
    conteo["conteo_delitos"] = conteo["conteo_delitos"].astype("int16")
    return conteo


def agregar_lags_y_rolling(tabla: pd.DataFrame) -> pd.DataFrame:
    tabla = tabla.sort_values(["hex_id", "turno", "semana"])
    g = tabla.groupby(["hex_id", "turno"], observed=True)["conteo_delitos"]

    tabla["lag_1sem"] = g.shift(1)
    tabla["lag_4sem"] = g.shift(4)
    tabla["lag_52sem"] = g.shift(52)
    tabla["roll_4sem_sum"] = g.transform(lambda s: s.shift(1).rolling(4, min_periods=1).sum())
    tabla["roll_12sem_sum"] = g.transform(lambda s: s.shift(1).rolling(12, min_periods=1).sum())
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

    pivot = tabla.pivot_table(index=["semana", "turno"], columns="hex_id", values="roll_4sem_sum", observed=True)
    pivot = pivot.reindex(columns=hex_ids, fill_value=0).fillna(0)
    mat = pivot.to_numpy(dtype="float32")

    vecino_k1 = mat @ adj_k1.T
    vecino_k2 = mat @ adj_k2.T

    vecino_k1_df = pd.DataFrame(vecino_k1, index=pivot.index, columns=hex_ids).stack().rename("vecino_k1_roll4")
    vecino_k2_df = pd.DataFrame(vecino_k2, index=pivot.index, columns=hex_ids).stack().rename("vecino_k2_roll4")
    vecinos = pd.concat([vecino_k1_df, vecino_k2_df], axis=1).reset_index()
    vecinos = vecinos.rename(columns={"level_2": "hex_id"})

    tabla = tabla.merge(vecinos, on=["semana", "turno", "hex_id"], how="left")
    return tabla


def agregar_socioeconomico_e_infraestructura(tabla: pd.DataFrame, hexes: pd.DataFrame) -> pd.DataFrame:
    radios = pd.read_parquet(PROCESSED / "radios_censales.parquet")[["id_radio", "pct_hogares_nbi"]]
    hexes = hexes.merge(radios, left_on="radio_censal_id", right_on="id_radio", how="left").drop(columns="id_radio")

    comuna_socio = pd.read_parquet(PROCESSED / "socioeconomico_comuna.parquet")
    comuna_socio = comuna_socio.rename(columns={"comuna": "comuna_id"})[["comuna_id", "pct_hacinamiento_critico"]]
    hexes = hexes.merge(comuna_socio, on="comuna_id", how="left")

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
    tabla["semana_del_anio"] = tabla["semana"].dt.isocalendar().week.astype("int8")
    tabla["mes"] = tabla["semana"].dt.month.astype("int8")

    feriados = set()
    for anio in ANIOS_FERIADOS:
        resp = requests.get(f"https://api.argentinadatos.com/v1/feriados/{anio}", timeout=30)
        if resp.ok:
            feriados |= {f["fecha"] for f in resp.json()}
    feriados_fecha = pd.to_datetime(sorted(feriados))

    semana_tiene_feriado = {}
    for s in tabla["semana"].unique():
        rango = pd.date_range(s, s + pd.Timedelta(days=6))
        semana_tiene_feriado[s] = bool(set(rango) & set(feriados_fecha))
    tabla["semana_con_feriado"] = tabla["semana"].map(semana_tiene_feriado)
    print(f"Feriados cargados: {len(feriados)} (2016-2026)")
    return tabla


def main() -> None:
    hexes = cargar_hexes_validos()
    hex_ids = sorted(hexes["hex_id"].tolist())

    tabla = armar_grilla_densa(hex_ids)

    conteo = cargar_conteo_semanal()
    tabla = tabla.merge(conteo, on=["hex_id", "semana", "turno"], how="left")
    tabla["conteo_delitos"] = tabla["conteo_delitos"].fillna(0).astype("int16")

    print("Calculando lags/rolling semanales...")
    tabla = agregar_lags_y_rolling(tabla)

    print("Calculando vecindad espacial (k=1, k=2)...")
    tabla = agregar_vecindad_espacial(tabla, hex_ids)

    print("Agregando socioeconómico e infraestructura...")
    tabla = agregar_socioeconomico_e_infraestructura(tabla, hexes)

    print("Agregando calendario...")
    tabla = agregar_calendario(tabla)

    FEATURES.mkdir(parents=True, exist_ok=True)
    tabla.to_parquet(FEATURES / "training_table_semanal.parquet", index=False)
    print(f"\nGuardado: training_table_semanal.parquet, {len(tabla):,} filas, "
          f"{tabla.memory_usage(deep=True).sum() / 1e6:.0f} MB en memoria")
    print(f"conteo_delitos: media={tabla['conteo_delitos'].mean():.3f}, "
          f"% ceros={(tabla['conteo_delitos'] == 0).mean():.1%}")


if __name__ == "__main__":
    main()
