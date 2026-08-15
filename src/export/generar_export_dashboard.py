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
                           cantidad de hexágonos. Además el riesgo por turno de
                           cada superficie por tipo y los delitos 2025 por tipo,
                           para el filtro de tipo de delito del tablero.
- comunas_resumen.json     lo mismo agregado a las 15 comunas, para los filtros
                           y la tabla de detalle.
- curva_k.json             cobertura del Módulo A para cada K — lo que hace que
                           el control de patrullas del tablero sea real y no una
                           interpolación.
- sensibilidad_radio.json  el barrido de radio, para poder mostrar de qué
                           depende el número.
- serie_delitos.json       serie mensual por tipo, 2016-2025, para las
                           tendencias y el contexto del quiebre de 2025.
- perfil_temporal.json     cuándo ocurren: por hora, por día de la semana y por
                           turno, cortado por tipo. Es lo que alimenta los
                           indicadores de frecuencia del tablero.
- resumen.json             los números sueltos que van en las tarjetas de KPI,
                           en un solo lugar en vez de hardcodeados en el front.
"""

from __future__ import annotations

import calendar
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

# Los cuatro tipos que tienen superficie de riesgo propia en
# riesgo_predicho_por_tipo.parquet. Vialidad y Homicidios quedaron afuera de esa
# superficie por decisión medida, no por olvido (ver README, "Riesgo por tipo en
# los módulos"): vialidad son siniestros viales y no delitos de seguridad, y
# homicidios tiene 78 hechos en el año de test. Igual se cuentan sus delitos:
# el tablero los ofrece en el filtro y avisa que ahí dibuja el riesgo agregado.
TIPOS_CON_SUPERFICIE = ["robo", "hurto", "lesiones", "amenazas"]

# Como aparecen escritos en la columna `tipo` de delitos_hex.
TIPOS_DELITO = ["Robo", "Hurto", "Lesiones", "Amenazas", "Vialidad", "Homicidios"]
TIPO_KEY = {t: t.lower() for t in TIPOS_DELITO}


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


def _riesgo_por_tipo_por_hex() -> pd.DataFrame:
    """hex_id × turno -> un score por tipo, en columnas `{tipo}__{turno}`.

    Mismo pivot que `_riesgo_por_hex` pero sobre las cuatro superficies por
    tipo. Se aplana a una columna por combinación en vez de dejar un MultiIndex
    porque después hay que hacer un `groupby(...).agg()` por barrio, y nombrar
    agregaciones sobre columnas de tuplas es una fuente de errores silenciosos.
    """
    riesgo = pd.read_parquet(FEATURES / "riesgo_predicho_por_tipo.parquet")
    riesgo["hex_id"] = riesgo["hex_id"].astype(str)
    riesgo["turno"] = riesgo["turno"].astype(str)

    salida = pd.DataFrame(index=pd.Index(riesgo["hex_id"].unique(), name="hex_id"))
    for tipo in TIPOS_CON_SUPERFICIE:
        pivot = riesgo.pivot(index="hex_id", columns="turno", values=f"score_{tipo}")
        pivot.columns = [f"{tipo}__{c}" for c in pivot.columns]
        salida = salida.join(pivot)

    hexes = (pd.read_parquet(FEATURES / "hex_maestra.parquet")
             .dropna(subset=["barrio_id"])[["hex_id", "barrio_id", "comuna_id"]])
    hexes["hex_id"] = hexes["hex_id"].astype(str)
    hexes["barrio_id"] = hexes["barrio_id"].astype(str)
    return hexes.merge(salida, left_on="hex_id", right_index=True, how="left").fillna(0)


def _delitos_por_barrio_y_tipo() -> pd.DataFrame:
    """barrio × tipo -> conteo del último año. Las columnas son los tipos."""
    d = delitos()
    tabla = (d.loc[d["anio"] == ANIO_ULTIMO]
             .groupby(["barrio", "tipo"], observed=True).size().unstack(fill_value=0))
    return tabla.reindex(columns=TIPOS_DELITO, fill_value=0)


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
                            columns=["fecha", "barrio", "comuna", "tipo", "franja", "dia", "turno"])
        f = pd.to_datetime(d["fecha"], errors="coerce")
        _DELITOS = pd.DataFrame({
            "anio": f.dt.year.astype("int16"),
            "mes": f.dt.month.astype("int8"),
            "barrio": d["barrio"].astype(str).str.upper().str.strip().astype("category"),
            "comuna": pd.to_numeric(d["comuna"], errors="coerce"),
            "tipo": d["tipo"].astype("category"),
            # -1 marca la hora desconocida (148 casos en 2025). Se guarda como
            # valor y no como NaN para poder dejar la columna en int8: un solo
            # NaN la promovería a float64 y son 1,35M de filas.
            "franja": pd.to_numeric(d["franja"], errors="coerce").fillna(-1).astype("int8"),
            "dia": d["dia"].astype(str).str.upper().str.strip().astype("category"),
            "turno": d["turno"].astype("category"),
        })
        del d, f
    return _DELITOS


def _poblacion_por_hex() -> pd.DataFrame:
    """hex_id -> población, con su barrio y comuna. Es lo que permite pasar de
    conteos crudos a tasa cada 100.000 habitantes, que es lo único comparable
    entre barrios de tamaño muy distinto (Palermo tiene 226.534 habitantes y
    Villa Real 5.500: el conteo crudo mide sobre todo cuánta gente vive ahí).

    La población ya viene prorrateada por área dentro del barrio desde
    `overlay_poligonos.py`; la suma da exacto los 2.890.151 del padrón.
    """
    hexes = (pd.read_parquet(FEATURES / "hex_maestra.parquet")
             .dropna(subset=["barrio_id"])[["hex_id", "barrio_id", "comuna_id"]])
    pob = pd.read_parquet(FEATURES / "hex_poblacion.parquet")
    return hexes.merge(pob, on="hex_id", how="left").fillna({"poblacion_hex": 0.0})


def _presion_visitantes() -> tuple[pd.Series, pd.Series]:
    """Percentil de afluencia no residente, por barrio y por comuna.

    La tasa cada 100.000 mide sobre población *residente*, así que se infla
    donde entra mucha gente que no vive ahí: San Nicolás tiene 29.273 vecinos y
    la tasa más alta de la Ciudad. Esto no corrige la tasa —marca dónde hay que
    leerla con pinzas.

    Por qué un percentil y no una población flotante estimada: se probó usar los
    molinetes como denominador y no se sostiene. Solo 23 de los 48 barrios
    tienen estación de subte, y esos 23 concentran apenas dos tercios de los
    delitos, así que la corrección se aplicaría a media ciudad y no a la otra
    media. Peor: Puerto Madero, el caso de manual de población flotante, no
    tiene subte — corregir por molinetes lo dejaba primero en el ranking, o sea
    exactamente al revés. EcoBici sí llega a los 48 barrios, pero sus magnitudes
    (46M de viajes) no son sumables con las del subte (2.730M de pasajeros).

    La salida es entonces el promedio de los percentiles de ambas fuentes,
    relativizado por población — el mismo criterio de rank que ya usa
    `modulo_b_camaras.py` por la misma razón de escalas incomparables.
    """
    h = _poblacion_por_hex()
    fl = pd.read_parquet(FEATURES / "hex_flujo_turno.parquet")
    fl["hex_id"] = fl["hex_id"].astype(str)
    h = h.copy()
    h["hex_id"] = h["hex_id"].astype(str)

    def por(nivel: str) -> pd.Series:
        base = (fl.merge(h, on="hex_id", how="inner")
                .groupby(nivel)[["flujo_ecobici", "flujo_molinetes"]].sum())
        pobl = h.groupby(nivel)["poblacion_hex"].sum()
        # cada fuente se lleva a fracción del total de la Ciudad antes de
        # promediar; si no, el subte domina por tres órdenes de magnitud
        cuota = (base["flujo_ecobici"] / base["flujo_ecobici"].sum()
                 + base["flujo_molinetes"] / base["flujo_molinetes"].sum()) / 2
        return (cuota / pobl.replace(0, pd.NA)).rank(pct=True)

    return por("barrio_id"), por("comuna_id")


def _delitos_por_barrio() -> pd.Series:
    d = delitos()
    return d.loc[d["anio"] == ANIO_ULTIMO, "barrio"].value_counts()


def _delitos_de(nombre: str, conteo: pd.Series) -> int:
    clave = ALIAS_BARRIO.get(nombre.upper(), nombre.upper())
    return int(conteo.get(clave, 0))


def exportar_barrios() -> None:
    barrios = pd.read_parquet(PROCESSED / "barrios.parquet")
    por_hex = _riesgo_por_hex()
    por_tipo = _riesgo_por_tipo_por_hex()
    por_barrio = _delitos_por_barrio()   # ojo: no llamarlo `delitos`, tapa a la función
    delitos_tipo = _delitos_por_barrio_y_tipo()
    pob_barrio = _poblacion_por_hex().groupby("barrio_id")["poblacion_hex"].sum()
    presion_barrio, _ = _presion_visitantes()

    # promedio por hexágono, no suma: los barrios varían mucho en superficie y
    # sumar convierte el mapa en un mapa de tamaños. El total se guarda aparte
    # porque para asignar recursos sí importa el volumen.
    agg = por_hex.groupby("barrio_id").agg(
        n_hex=("hex_id", "size"), comuna=("comuna_id", "first"),
        **{f"m_{t}": (t, "mean") for t in TURNOS if t in por_hex.columns},
        **{f"s_{t}": (t, "sum") for t in TURNOS if t in por_hex.columns},
    )
    cols_tipo = [f"{tp}__{t}" for tp in TIPOS_CON_SUPERFICIE for t in TURNOS
                 if f"{tp}__{t}" in por_tipo.columns]
    agg_tipo = por_tipo.groupby("barrio_id")[cols_tipo].mean()

    features = []
    for _, b in barrios.iterrows():
        nombre = str(b["nombre"]).strip()
        fila = agg.loc[nombre] if nombre in agg.index else None
        fila_tipo = agg_tipo.loc[nombre] if nombre in agg_tipo.index else None
        props = {
            "nombre": nombre,
            "comuna": int(fila["comuna"]) if fila is not None else None,
            "n_hex": int(fila["n_hex"]) if fila is not None else 0,
            "delitos_2025": _delitos_de(nombre, por_barrio),
            "poblacion": int(round(float(pob_barrio.get(nombre, 0.0)))),
            "presion_visitantes": (round(float(presion_barrio[nombre]), 3)
                                   if nombre in presion_barrio.index
                                   and pd.notna(presion_barrio[nombre]) else None),
        }
        for t in TURNOS:
            k = TURNO_KEY[t]
            props[f"riesgo_{k}"] = round(float(fila[f"m_{t}"]), 5) if fila is not None else 0.0
            props[f"riesgo_total_{k}"] = round(float(fila[f"s_{t}"]), 4) if fila is not None else 0.0
            for tp in TIPOS_CON_SUPERFICIE:
                col = f"{tp}__{t}"
                props[f"riesgo_{tp}_{k}"] = (
                    round(float(fila_tipo[col]), 5)
                    if fila_tipo is not None and col in agg_tipo.columns else 0.0)
        clave = ALIAS_BARRIO.get(nombre.upper(), nombre.upper())
        for tp in TIPOS_DELITO:
            props[f"delitos_{TIPO_KEY[tp]}"] = (
                int(delitos_tipo.loc[clave, tp]) if clave in delitos_tipo.index else 0)
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
    por_tipo = _riesgo_por_tipo_por_hex().set_index("hex_id")
    d = delitos()
    dd = d.loc[(d["anio"] == ANIO_ULTIMO) & d["comuna"].notna()].copy()
    dd["comuna"] = dd["comuna"].astype(int)
    por_comuna = dd["comuna"].value_counts()
    por_comuna_tipo = (dd.groupby(["comuna", "tipo"], observed=True).size()
                       .unstack(fill_value=0).reindex(columns=TIPOS_DELITO, fill_value=0))

    pob_comuna = _poblacion_por_hex().groupby("comuna_id")["poblacion_hex"].sum()
    _, presion_comuna = _presion_visitantes()

    filas = []
    for comuna, g in por_hex.groupby("comuna_id"):
        gt = por_tipo.loc[por_tipo.index.intersection(g["hex_id"])]
        fila = {"comuna": int(comuna), "n_hex": int(len(g)),
                "n_barrios": int(g["barrio_id"].nunique()),
                "delitos_2025": int(por_comuna.get(int(comuna), 0)),
                "poblacion": int(round(float(pob_comuna.get(comuna, 0.0)))),
                "presion_visitantes": (round(float(presion_comuna[comuna]), 3)
                                       if comuna in presion_comuna.index
                                       and pd.notna(presion_comuna[comuna]) else None)}
        for t in TURNOS:
            if t in g.columns:
                fila[f"riesgo_{TURNO_KEY[t]}"] = round(float(g[t].mean()), 5)
            for tp in TIPOS_CON_SUPERFICIE:
                col = f"{tp}__{t}"
                if col in gt.columns:
                    fila[f"riesgo_{tp}_{TURNO_KEY[t]}"] = round(float(gt[col].mean()), 5)
        for tp in TIPOS_DELITO:
            fila[f"delitos_{TIPO_KEY[tp]}"] = (
                int(por_comuna_tipo.loc[int(comuna), tp])
                if int(comuna) in por_comuna_tipo.index else 0)
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


DIAS_ORDEN = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO"]


def exportar_perfil_temporal() -> None:
    """Cuándo ocurren los delitos: por hora, por día de la semana y por turno.

    Todo cortado por tipo además del total, porque el tablero filtra por tipo y
    un perfil horario que no siguiera el filtro sería peor que no tenerlo: el
    perfil de vialidad y el de robo no se parecen en nada.

    Los conteos van crudos y no en porcentaje: el front necesita el total para
    calcular la cascada de frecuencias, y dejar que divida él evita tener dos
    redondeos distintos del mismo número.
    """
    d = delitos()
    ult = d.loc[d["anio"] == ANIO_ULTIMO]

    def cortes(col: str, orden: list) -> dict:
        """{tipo -> [conteo por cada valor de `orden`]}, con 'todos' incluido."""
        salida: dict[str, list[int]] = {}
        tabla = ult.groupby([col, "tipo"], observed=True).size().unstack(fill_value=0)
        tabla = tabla.reindex(index=orden, fill_value=0).reindex(columns=TIPOS_DELITO, fill_value=0)
        salida["todos"] = [int(v) for v in tabla.sum(axis=1)]
        for tp in TIPOS_DELITO:
            salida[TIPO_KEY[tp]] = [int(v) for v in tabla[tp]]
        return salida

    totales = {"todos": int(len(ult))}
    for tp in TIPOS_DELITO:
        totales[TIPO_KEY[tp]] = int((ult["tipo"] == tp).sum())

    # los días efectivamente cubiertos, no 365 fijo: se suman los largos de los
    # meses presentes. Si el último año viniera cortado, dividir por 365
    # subestimaría la frecuencia y la cascada del tablero quedaría mal
    dias = sum(calendar.monthrange(ANIO_ULTIMO, int(m))[1]
               for m in sorted(ult["mes"].unique()))

    perfil = {
        "anio": ANIO_ULTIMO,
        "dias": dias,
        "totales": totales,
        # -1 es la hora desconocida; se excluye del perfil horario para no
        # dibujar una barra fantasma, pero sigue contando en los totales
        "franja": cortes("franja", list(range(24))),
        "dia_semana": cortes("dia", DIAS_ORDEN),
        "turno": cortes("turno", ["Mañana", "Tarde", "Noche", "Madrugada"]),
        "dias_orden": [d.capitalize() for d in DIAS_ORDEN],
    }
    (OUT / "perfil_temporal.json").write_text(
        json.dumps(perfil, ensure_ascii=False), encoding="utf-8")
    print(f"perfil_temporal.json: {dias} días, {totales['todos']} delitos")


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
    exportar_perfil_temporal()
    exportar_resumen()
    print(f"\nTodo en {OUT}")


if __name__ == "__main__":
    main()
