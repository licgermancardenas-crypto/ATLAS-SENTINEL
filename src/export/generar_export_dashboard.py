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
- cobertura_poblacion.json cuanta *gente* cubre el Modulo A, no solo cuanto
                           riesgo, y cuanto cambiaria el plan si el objetivo
                           fuera la poblacion en vez del riesgo.
- demografia.json          cuanta gente vive en cada barrio y comuna, con el
                           corte por sexo (Censo 2010) y la estructura etaria
                           por comuna (Censo 2022). Dos censos distintos, cada
                           uno con su anio adentro.
- pronostico.json          el pronóstico mensual de Ciudad para 2026 con los
                           cuatro modelos del backtest, sus bandas y el error
                           medido de cada uno. Va con el backtest adentro
                           porque un pronóstico sin su error no se puede leer.
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
    exactamente al revés. Las magnitudes tampoco son sumables entre sí: EcoBici
    son 46M de viajes, el subte 2.730M de pasajeros y el tren 107M de boletos.

    La salida es entonces el promedio de las cuotas de las tres fuentes,
    relativizado por población — el mismo criterio de rank que ya usa
    `modulo_b_camaras.py` por la misma razón de escalas incomparables.

    El tren entró después que las otras dos, y por un motivo medido: validando
    el índice contra la ENMODO 2018 (`src/validation/validar_presion_visitantes.py`)
    la Comuna 9 —Liniers, Mataderos— salía 4ª en la encuesta y 14ª acá, porque
    con solo subte y bici no se ve un nodo al que se llega en tren.
    """
    h = _poblacion_por_hex().copy()
    h["hex_id"] = h["hex_id"].astype(str)

    fl = pd.read_parquet(FEATURES / "hex_flujo_turno.parquet")
    fl["hex_id"] = fl["hex_id"].astype(str)
    flujo = fl.groupby("hex_id")[["flujo_ecobici", "flujo_molinetes"]].sum()

    # el tren no pasa por hex_flujo_turno: esa tabla alimenta el feature set del
    # modelo y sumarlo ahí obligaría a reentrenar. Acá se lee aparte.
    tr = pd.read_parquet(FEATURES / "trenes_estaciones_hex.parquet")
    tr["hex_id"] = tr["hex_id"].astype(str)
    flujo["flujo_trenes"] = tr.groupby("hex_id")["pax"].sum()
    flujo = flujo.fillna(0.0)

    # el colectivo entra ya agregado por barrio y no por hexágono: SUBE informa
    # por línea, así que el reparto a paradas es un supuesto uniforme (ver
    # `pipeline/ingest_colectivos_sube.py`) y bajarlo a hexágono le daría una
    # precisión que el método no tiene
    col = pd.read_parquet(FEATURES / "colectivos_barrio.parquet")
    barrio_a_comuna = h.groupby("barrio_id")["comuna_id"].first()

    FUENTES = ["flujo_ecobici", "flujo_molinetes", "flujo_trenes"]

    def por(nivel: str) -> pd.Series:
        base = (flujo.join(h.set_index("hex_id")[[nivel]], how="inner")
                .groupby(nivel)[FUENTES].sum())
        base["flujo_colectivos"] = (
            col.set_index("barrio")["pax"] if nivel == "barrio_id"
            else col.assign(c=col["barrio"].map(barrio_a_comuna)).groupby("c")["pax"].sum())
        base = base.fillna(0.0)
        pobl = h.groupby(nivel)["poblacion_hex"].sum()
        # cada fuente se lleva a fracción del total de la Ciudad antes de
        # promediar; si no, el colectivo y el subte se comen a la bici por
        # órdenes de magnitud
        fuentes = FUENTES + ["flujo_colectivos"]
        cuota = sum(base[f] / base[f].sum() for f in fuentes) / len(fuentes)
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


# ────────────────────────────────────────────── pronóstico mensual de Ciudad

# Los cuatro modelos del backtest, en el orden en que conviene leerlos: primero
# el que se usa, último el port literal que falla. El texto es el que explica
# por qué están los cuatro y no solo el ganador — la conclusión del README es
# que ninguno gana en todos los horizontes, y eso hay que poder verlo.
MODELOS_FORECAST: list[tuple[str, str, str]] = [
    ("prophet_regimen", "Prophet con regímenes",
     "Prophet con la pandemia y el escalón de 2025 como indicadoras multiplicativas. "
     "Es el que menos error tiene en meses normales y a horizontes de 3 a 6 meses."),
    ("ets", "Holt-Winters",
     "Suavizado exponencial con estacionalidad. Es el mejor a un mes vista."),
    ("naive_estacional", "El mismo mes del año pasado",
     "El baseline. A doce meses no hay modelo que le gane: cuanto más lejos se "
     "mira, más pesa la estacionalidad pelada."),
    ("prophet", "Prophet, port literal",
     "Prophet sin regresores de régimen, como en el proyecto de LAPD. Lee la "
     "recuperación pos-pandemia como tendencia y la extrapola: más del doble de error."),
]
MODELO_ELEGIDO = "prophet_regimen"
ANIO_PRONOSTICO = 2026


def _meses(df: pd.DataFrame, col_lo: str, col_hi: str) -> list[dict]:
    """Las doce filas de un pronóstico, ordenadas y redondeadas a delito entero.

    Se redondea acá y no en el front: son conteos de hechos, y un decimal en un
    número que ya tiene una banda de ±1.400 finge una precisión que no existe.
    """
    filas = df.sort_values("ds")
    return [{"mes": int(r.ds.month), "yhat": round(float(r.yhat)),
             "lo": round(float(getattr(r, col_lo))), "hi": round(float(getattr(r, col_hi)))}
            for r in filas.itertuples()]


def exportar_pronostico() -> None:
    """El pronóstico mensual de Ciudad, con su backtest, para el tablero.

    Tres cosas van juntas y no se pueden separar sin volver el número engañoso:
    el pronóstico, la banda, y el error medido del modelo que lo produjo. Un
    "10.993 delitos por mes en 2026" solo significa algo al lado de "y su error
    típico es de 971 en un mes normal, 1.360 en el año del quiebre".

    Por eso el JSON lleva los cuatro modelos y no solo el elegido: el hallazgo
    del backtest es que el ganador cambia con el horizonte y que a doce meses
    gana el baseline. Mostrar un solo modelo escondería justo eso.
    """
    fc = FEATURES / "forecast_mensual_2026.parquet"
    bt_path = FEATURES / "forecast_mensual_backtest.parquet"
    tipos_path = FEATURES / "forecast_mensual_por_tipo.parquet"
    if not (fc.exists() and bt_path.exists() and tipos_path.exists()):
        print("pronostico.json: faltan los parquet de forecast_mensual — se omite")
        return

    pron = pd.read_parquet(fc)
    bt = pd.read_parquet(bt_path)
    por_tipo = pd.read_parquet(tipos_path)

    bt = bt.assign(ae=bt["error"].abs(), ape=bt["error"].abs() / bt["real"] * 100)
    normal = bt[bt["periodo"] == "normal"]
    quiebre = bt[bt["periodo"] == "quiebre 2025"]

    # la base contra la que se compara el pronóstico es el último año cerrado,
    # el mismo que usan las tarjetas de KPI
    por_anio = delitos()["anio"].value_counts().sort_index()
    base_total = int(por_anio.loc[ANIO_ULTIMO])
    base_mensual = base_total / 12

    modelos = []
    for key, label, nota in MODELOS_FORECAST:
        p = pron[pron["modelo"] == key]
        n = normal[normal["modelo"] == key]
        q = quiebre[quiebre["modelo"] == key]
        mensual = float(p["yhat"].mean())
        modelos.append({
            "key": key, "label": label, "nota": nota,
            "mensual": round(mensual),
            "total": round(float(p["yhat"].sum())),
            "vs_base": mensual / base_mensual - 1,
            "banda": [round(float(p["yhat_lower"].mean())), round(float(p["yhat_upper"].mean()))],
            "mae_normal": round(float(n["ae"].mean()), 1),
            "mape_normal": float(n["ape"].mean()) / 100,
            "sesgo_normal": round(float(n["error"].mean()), 1),
            "cobertura_normal": float(n["dentro"].mean()),
            "mae_quiebre": round(float(q["ae"].mean()), 1),
            "sesgo_quiebre": round(float(q["error"].mean()), 1),
            "mae_por_h": [round(float(v)) for v in
                          n.groupby("h")["ae"].mean().reindex(range(1, 13)).tolist()],
            "meses": _meses(p, "yhat_lower", "yhat_upper"),
        })

    # el pronóstico por tipo corre solo con el modelo elegido: son seis series
    # más cortas y con menos nivel, y comparar cuatro modelos en cada una no
    # cambiaría la lectura. La banda es la nativa, igual que en el agregado.
    tipos = []
    for tipo in TIPOS_DELITO:
        t = por_tipo[por_tipo["tipo"] == tipo]
        if t.empty:
            continue
        mensual = float(t["yhat"].mean())
        base_tipo = float(t["prom_ult12"].iloc[0])
        tipos.append({
            "key": TIPO_KEY[tipo], "label": tipo,
            "mensual": round(mensual),
            "base_mensual": round(base_tipo),
            "vs_base": mensual / base_tipo - 1 if base_tipo > 0 else None,
            "banda": [round(float(t["yhat_lower"].mean())), round(float(t["yhat_upper"].mean()))],
            "meses": _meses(t, "yhat_lower", "yhat_upper"),
        })

    salida = {
        "anio": ANIO_PRONOSTICO,
        "elegido": MODELO_ELEGIDO,
        "base": {"anio": ANIO_ULTIMO, "total": base_total, "mensual": round(base_mensual)},
        "backtest": {
            "n_origenes": int(bt["origen"].nunique()),
            "desde": str(bt["origen"].min().date()),
            "hasta": str(bt["origen"].max().date()),
            "horizonte": int(bt["h"].max()),
            # pares origen-objetivo por modelo, no meses: cada origen deja
            # hasta doce objetivos y varios orígenes apuntan al mismo mes
            "n_evaluaciones_normales": int(len(normal) / len(MODELOS_FORECAST)),
        },
        "modelos": modelos,
        "por_tipo": tipos,
        "salvedad":
            "Pronostica delito registrado, no delito. El nivel de 2025 quedó bajo revisión "
            "y un pronóstico de volumen es una afirmación sobre niveles, así que hereda "
            "entera esa salvedad: sirve para dimensionar carga de trabajo sobre el sistema "
            "de denuncias, no para decir cuánto delito va a sufrir la gente.",
    }
    (OUT / "pronostico.json").write_text(json.dumps(salida, ensure_ascii=False),
                                         encoding="utf-8")
    print(f"pronostico.json: {len(modelos)} modelos, {len(tipos)} tipos, "
          f"{salida['backtest']['n_origenes']} orígenes de backtest")

# ──────────────────────────────────────────────── demografía (población, sexo, edad)

# Los dos censos que entran acá, y por qué no se pueden fusionar en un número.
# La población por barrio y el corte por sexo son Censo 2010 (es el año de
# `radios_censales`, que también es el de NBI y hacinamiento). La estructura
# etaria es Censo 2022, el único que la publica por comuna. Entre los dos hay
# 231.556 personas de diferencia. Cada bloque del JSON lleva su año adentro y
# el tablero lo muestra pegado al número, en vez de dejar que alguien sume
# 2.890.151 habitantes con un 17,3% de mayores de 65 y crea que el resultado
# es una cuenta de 2022.
ANIO_POBLACION = 2010
ANIO_EDAD = 2022


def _areas_km2() -> tuple[pd.Series, pd.Series]:
    """Superficie por barrio y por comuna, para la densidad."""
    b = pd.read_parquet(PROCESSED / "barrios.parquet")
    km2 = b["area_m2"] / 1e6
    por_barrio = pd.Series(km2.values, index=b["nombre"])
    por_comuna = km2.groupby(b["comuna"].astype(int)).sum()
    return por_barrio, por_comuna


def exportar_demografia() -> None:
    """Cuánta gente vive en cada zona, de qué sexo y de qué edad.

    Va en un archivo aparte y no dentro de `barrios_riesgo.geojson` por dos
    razones. La primera es de peso: el geojson son 135 KB de polígonos que el
    mapa necesita en el primer render, y la demografía no la necesita nadie
    hasta que se abre el panel. La segunda es que la edad **no existe por
    barrio** — solo por comuna — así que meterla en el geojson obligaría a
    dejar 48 campos en null y a que cada componente decidiera por su cuenta
    qué hacer con eso.
    """
    demo = PROCESSED / "demografia_comuna.parquet"
    sexo_b = PROCESSED / "socio_barrio.parquet"
    if not (demo.exists() and sexo_b.exists()):
        print("demografia.json: falta correr pipeline/ingest_demografia.py — se omite")
        return

    edad = pd.read_parquet(demo)
    sb = pd.read_parquet(sexo_b)
    sc = pd.read_parquet(PROCESSED / "socio_comuna.parquet")
    # Hacinamiento es el único indicador socioeconómico que **solo** existe por
    # comuna: no está en `radios_censales`, así que no hay forma de bajarlo a
    # barrio sin inventarlo. Se lee directo del archivo de GCBA.
    hac = pd.read_parquet(PROCESSED / "socioeconomico_comuna.parquet").set_index("comuna")
    km2_barrio, km2_comuna = _areas_km2()

    comuna_de = (pd.read_parquet(PROCESSED / "barrios.parquet")
                 .set_index("nombre")["comuna"].astype(int))

    barrios = []
    for r in sb.sort_values("poblacion_total", ascending=False).itertuples():
        area = float(km2_barrio.get(r.barrio, float("nan")))
        util = area == area and area > 0
        barrios.append({
            "nombre": r.barrio,
            "comuna": int(comuna_de.get(r.barrio, 0)) or None,
            "poblacion": int(r.poblacion_total),
            "varones": int(r.poblacion_varones),
            "mujeres": int(r.poblacion_mujeres),
            "area_km2": round(area, 2) if util else None,
            "densidad": round(r.poblacion_total / area) if util else None,
            "hogares": int(r.hogares_total),
            "hogares_nbi": int(r.hogares_con_nbi),
            "pct_nbi": float(r.pct_hogares_nbi),
        })

    edad = edad.set_index("comuna")
    comunas = []
    for r in sc.sort_values("poblacion_total", ascending=False).itertuples():
        c = int(r.comuna)
        area = float(km2_comuna.get(c, float("nan")))
        util = area == area and area > 0
        e = edad.loc[c]
        comunas.append({
            "comuna": c,
            "poblacion": int(r.poblacion_total),
            "varones": int(r.poblacion_varones),
            "mujeres": int(r.poblacion_mujeres),
            "area_km2": round(area, 2) if util else None,
            "densidad": round(r.poblacion_total / area) if util else None,
            "hogares": int(r.hogares_total),
            "hogares_nbi": int(r.hogares_con_nbi),
            "pct_nbi": float(r.pct_hogares_nbi),
            # el bloque de edad es del otro censo, por eso lleva su propia
            # población y no reusa la de arriba
            "poblacion_2022": int(e["poblacion_2022"]),
            "pct_0_14": round(float(e["pct_0_14"]), 1),
            "pct_15_64": round(float(e["pct_15_64"]), 1),
            "pct_65": round(float(e["pct_65"]), 1),
            "pct_80": round(float(e["pct_80"]), 1),
            "hab_0_14": int(e["hab_0_14"]),
            "hab_15_64": int(e["hab_15_64"]),
            "hab_65": int(e["hab_65"]),
            "envejecimiento": float(e["envejecimiento"]),
            "dependencia": float(e["dependencia"]),
            # los tres suman 100: se guardan los tres para que el tooltip pueda
            # mostrar el reparto y no solo la punta crítica
            "pct_sin_hacinamiento": float(hac.loc[c, "pct_sin_hacinamiento"]),
            "pct_hacinamiento_no_critico": float(hac.loc[c, "pct_hacinamiento_no_critico"]),
            "pct_hacinamiento_critico": float(hac.loc[c, "pct_hacinamiento_critico"]),
        })

    # el agregado de Ciudad se suma desde las comunas en vez de leer la fila
    # "Total" de INDEC: así, si alguna vez una comuna queda afuera, el total
    # del tablero baja con ella en lugar de seguir diciendo el número entero
    hab = {g: sum(c[f"hab_{g}"] for c in comunas) for g in ["0_14", "15_64", "65"]}
    pob22 = sum(c["poblacion_2022"] for c in comunas)
    pob10 = sum(c["poblacion"] for c in comunas)
    varones = sum(c["varones"] for c in comunas)
    mujeres = sum(c["mujeres"] for c in comunas)
    hogares = sum(c["hogares"] for c in comunas)
    hogares_nbi = sum(c["hogares_nbi"] for c in comunas)
    # el promedio de Ciudad se pondera por hogares y no por comuna: la 8 tiene
    # el doble de hogares que la 2 y pesar las quince igual daría un número que
    # no le corresponde a nadie
    hac_critico = sum(c["pct_hacinamiento_critico"] * c["hogares"] for c in comunas) / hogares
    km2 = float(km2_comuna.sum())

    miles = lambda n: f"{n:,}".replace(",", ".")

    salida = {
        "poblacion": {
            "anio": ANIO_POBLACION, "total": pob10, "varones": varones, "mujeres": mujeres,
            "area_km2": round(km2, 1), "densidad": round(pob10 / km2),
            "fuente": "Censo 2010 · radios censales",
        },
        "nbi": {
            "anio": ANIO_POBLACION, "hogares": hogares, "hogares_nbi": hogares_nbi,
            "pct": round(hogares_nbi / hogares * 100, 2),
            "fuente": "Censo 2010 · radios censales",
        },
        "hacinamiento": {
            "anio": ANIO_POBLACION, "pct_critico": round(hac_critico, 2),
            "fuente": "Censo 2010 · GCBA, solo por comuna",
        },
        "edad": {
            "anio": ANIO_EDAD, "total": pob22,
            "hab_0_14": hab["0_14"], "hab_15_64": hab["15_64"], "hab_65": hab["65"],
            "pct_0_14": round(hab["0_14"] / pob22 * 100, 1),
            "pct_15_64": round(hab["15_64"] / pob22 * 100, 1),
            "pct_65": round(hab["65"] / pob22 * 100, 1),
            "fuente": "Censo 2022 · INDEC, derivada de los índices por comuna",
        },
        "barrios": barrios,
        "comunas": comunas,
        "notas": {
            "edad_solo_comuna":
                "La estructura etaria solo existe por comuna. El Censo 2022 no está publicado "
                "por radio censal ni por barrio, así que al elegir un barrio se muestra la edad "
                "de su comuna, no la del barrio.",
            "edad_derivada":
                "INDEC no publica los grupos de edad por comuna: publica el % de 65 años y más "
                "y el índice de envejecimiento. Los tres grandes grupos se despejan de esos dos "
                "y se verifican recalculando el índice de dependencia contra el publicado — el "
                "desvío máximo sobre las 15 comunas es de 0,65 puntos, que es redondeo.",
            "dos_censos":
                f"Población y sexo son del Censo {ANIO_POBLACION}; la edad, del Censo {ANIO_EDAD}. "
                f"La Ciudad pasó de {miles(pob10)} a {miles(pob22)} habitantes entre los dos "
                "(+8,0%), así que los porcentajes de edad no se pueden aplicar a la población "
                "de 2010 para sacar cantidades de personas.",
            "nbi":
                "NBI es Necesidades Básicas Insatisfechas: un hogar tiene NBI si le falta alguna "
                "de cinco condiciones básicas (hacinamiento, vivienda precaria, sin baño, un "
                "chico sin escolarizar, o mucha carga por miembro que trabaja). Es del Censo "
                "2010 y mide pobreza estructural, no ingreso: no se mueve con la inflación ni "
                "con el ciclo económico, y por eso tampoco refleja los cambios de los últimos "
                "quince años. El porcentaje se calcula sobre hogares, no sobre personas.",
            "hacinamiento":
                "Un hogar tiene hacinamiento crítico cuando viven más de tres personas por "
                "cuarto, y no crítico entre dos y tres. Es el único indicador socioeconómico "
                "del tablero que solo existe por comuna: no está publicado por radio censal, "
                "así que no se puede bajar a barrio sin inventarlo.",
            "hacinamiento_senal_debil":
                "En la auditoría de equidad, el hacinamiento es la única variable cuya "
                "correlación con el riesgo predicho cambia de signo al controlar por historial "
                "delictivo (de 0,05 a −0,28). Está anotado como señal a vigilar, no como "
                "hallazgo: con quince comunas la correlación parcial tiene muy pocos grados de "
                "libertad y no alcanza para concluir en ningún sentido.",
            "nbi_no_es_riesgo":
                "El mapa de NBI no es un mapa de riesgo, y el proyecto lo tiene medido: la "
                "correlación entre NBI y el riesgo predicho por comuna cae de 0,41 a 0,14 al "
                "controlar por historial delictivo. La mayor parte de esa relación es indirecta. "
                "Ver la auditoría de equidad en el README.",
            "denominador":
                "Las tasas de delito del tablero siguen usando la población de 2010: es la única "
                "que existe por barrio y la única comparable con NBI y hacinamiento, que son del "
                "mismo censo.",
        },
    }
    (OUT / "demografia.json").write_text(json.dumps(salida, ensure_ascii=False),
                                         encoding="utf-8")
    print(f"demografia.json: {len(barrios)} barrios, {len(comunas)} comunas, "
          f"{miles(pob10)} hab. {ANIO_POBLACION} / {miles(pob22)} hab. {ANIO_EDAD}")

    _comunas_geojson(comunas)


def _comunas_geojson(comunas: list[dict]) -> None:
    """Los 15 polígonos de comuna, para pintar la edad en el mapa.

    **Por qué un polígono nuevo y no reusar el de barrios.** La edad solo
    existe por comuna. Pintando los 48 barrios con el valor de su comuna, el
    mapa muestra 48 formas donde hay 15 datos: los límites internos invitan a
    leer una diferencia entre Palermo y Colegiales que en el dato no está.
    Dibujar la unidad que el dato tiene evita esa lectura sin ninguna
    advertencia.

    No hay dataset de comunas con geometría en el repo: se disuelven los
    barrios, que es exacto porque cada barrio pertenece a una sola comuna.
    """
    from shapely.ops import unary_union

    b = pd.read_parquet(PROCESSED / "barrios.parquet")
    geoms = b["geometry_wkt"].apply(wkt.loads)
    por_comuna = b["comuna"].astype(int)

    features = []
    for c in comunas:
        union = unary_union(list(geoms[por_comuna == c["comuna"]]))
        # ~5 m de tolerancia. A este zoom no se distingue y baja el archivo a
        # la mitad; con `preserve_topology` no se abren huecos entre comunas.
        union = union.simplify(0.00005, preserve_topology=True)
        features.append({
            "type": "Feature",
            "geometry": mapping(union),
            "properties": {k: v for k, v in c.items()},
        })

    destino = OUT / "comunas.geojson"
    destino.write_text(json.dumps({"type": "FeatureCollection", "features": features}),
                       encoding="utf-8")
    print(f"comunas.geojson: {len(features)} polígonos, {destino.stat().st_size // 1024} KB")

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
    copiar_json(FEATURES / "cobertura_poblacion.json", "cobertura_poblacion.json")
    exportar_serie_delitos()
    exportar_perfil_temporal()
    exportar_pronostico()
    exportar_demografia()
    exportar_resumen()
    print(f"\nTodo en {OUT}")


if __name__ == "__main__":
    main()
