"""
Pronóstico mensual de delito registrado a nivel Ciudad, con origen deslizante.

POR QUÉ ESTE SCRIPT EXISTE
Todo lo que ATLAS tiene modelado hasta acá contesta *dónde*: hexágono × turno,
grano semanal, y las métricas que importan son de ranking (Recall@K, PAI, PEI).
Esta es la otra pregunta, la que el tablero no puede contestar hoy: **cuánto
delito registrado va a haber el mes que viene en toda la Ciudad**. Es una serie
única de 120 meses (2016-01 a 2025-12), no un problema espacial, y por eso el
modelo es de series de tiempo y no el LightGBM.

Replica el enfoque de `ml_forecast.py` del proyecto de LAPD (Prophet, horizonte
de 12 meses, apertura por categoría), con dos cambios deliberados:

1. **Los regímenes entran como regresores, no como tendencia.** La serie tiene
   dos perturbaciones enormes que no son tendencia: el pozo de la pandemia
   (mínimo 2.850 delitos en abril de 2020 contra ~12.500 normales) y el escalón
   de enero de 2025 (−16% de golpe, documentado en `quiebre_2025.py`). Prophet
   sin ayuda lee el escalón como pendiente y la extrapola: proyecta 2026 hacia
   abajo por un movimiento que ya ocurrió y se quedó quieto. Acá cada régimen es
   una variable indicadora multiplicativa, así que desplaza el nivel sin tocar
   la tendencia.

2. **La validación es de origen deslizante de verdad.** El script de LAPD titula
   "cross-validation" un gráfico que compara el ajuste in-sample contra los
   datos con los que se ajustó — eso mide memoria, no pronóstico. Acá se
   reentrena en cada origen y se predice a 1..12 meses vista, que es el mismo
   protocolo de `backtest_pronostico.py`.

LO QUE ESTE NÚMERO ES Y LO QUE NO ES
Pronostica **delito registrado**, no delito. La distinción no es un tecnicismo:
`quiebre_2025.py` concluyó que el nivel de 2025 no es confiable —las firmas
internas no son las de una caída puramente genuina y ninguna fuente
independiente del registro la acompaña— y dejó explícitamente inhabilitada
cualquier afirmación sobre niveles. Un pronóstico mensual de volumen *es* una
afirmación sobre niveles, así que hereda entera esa salvedad: sirve para
planificar carga de trabajo sobre el sistema de denuncias, no para decir cuánto
delito va a sufrir la gente.

El backtest tiene una regla que hace la diferencia entre medir y hacer trampa:
**un régimen solo existe para el modelo si ya había empezado en el origen**. En
un origen de diciembre de 2024 el escalón de enero de 2025 todavía no pasó, así
que ningún modelo lo ve venir y todos comen el error entero. Es lo correcto —
así se mide cuánto cuesta un quiebre, en vez de esconderlo.

Uso: python forecast_mensual.py
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
logging.getLogger("prophet").setLevel(logging.ERROR)

import numpy as np
import pandas as pd
from prophet import Prophet

# prophet reconfigura el logging de cmdstanpy al importarse, y son dos líneas
# INFO por ajuste: con ~180 ajustes en el backtest tapan toda la salida. Por eso
# el nivel se baja DESPUÉS del import — y hace falta además cortarle la
# propagación, porque prophet le deja su propio handler al logger.
_cs = logging.getLogger("cmdstanpy")
_cs.handlers.clear()
_cs.addHandler(logging.NullHandler())
_cs.propagate = False
_cs.setLevel(logging.ERROR)

RAIZ = Path(__file__).resolve().parent.parent.parent
DELITOS = RAIZ / "data" / "processed" / "delitos.parquet"
SALIDA = RAIZ / "data" / "features"

RUTA_BACKTEST = SALIDA / "forecast_mensual_backtest.parquet"
RUTA_PRONOSTICO = SALIDA / "forecast_mensual_2026.parquet"
RUTA_TIPOS = SALIDA / "forecast_mensual_por_tipo.parquet"

HORIZONTE = 12          # meses que se pronostican
MIN_HISTORIA = 36       # meses mínimos antes del primer origen del backtest
INTERVALO = 0.90        # ancho del intervalo de predicción
SEMILLA = 42            # Prophet muestrea las bandas: sin esto la cobertura
                        # reportada se mueve un par de puntos entre corridas

# Los tres regímenes. Las fechas de la pandemia salen de mirar la serie: el
# derrumbe arranca en marzo de 2020, la segunda ola hunde mayo de 2021 (7.246),
# y recién en octubre de 2022 la serie vuelve al orden de magnitud previo. El
# escalón de 2025 arranca en enero y sigue abierto — es el que documenta
# `quiebre_2025.py`.
REGIMENES = {
    "covid_duro":   ("2020-03-01", "2021-08-01"),
    "covid_recup":  ("2021-09-01", "2022-09-01"),
    "regimen_2025": ("2025-01-01", None),        # None = sigue abierto
}


# ────────────────────────────────────────────────────────────────────── datos

def cargar() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Serie mensual total y serie mensual por tipo de delito.

    `cantidad` se suma en vez de contar filas porque el parquet trae una columna
    de cantidad que no siempre vale 1.
    """
    d = pd.read_parquet(DELITOS, columns=["fecha", "tipo", "cantidad"])
    d["mes"] = d["fecha"].dt.to_period("M").dt.to_timestamp()

    total = (d.groupby("mes", as_index=False)["cantidad"].sum()
             .rename(columns={"mes": "ds", "cantidad": "y"}).sort_values("ds"))
    por_tipo = (d.groupby(["tipo", "mes"], as_index=False)["cantidad"].sum()
                .rename(columns={"mes": "ds", "cantidad": "y"}))
    return total.reset_index(drop=True), por_tipo


def regresores(fechas: pd.Series, origen: pd.Timestamp) -> pd.DataFrame:
    """Indicadoras de régimen, construidas con lo que se sabía en `origen`.

    Dos reglas, las dos por honestidad del backtest:

    - Un régimen que todavía no empezó en `origen` no existe: la columna se
      omite entera. Nadie puede anticipar un quiebre.
    - Un régimen **todavía activo** en `origen` se extiende hacia el futuro sin
      final. Se sabe que se está adentro; no se sabe cuándo termina. Ponerle la
      fecha real de salida sería filtrar el futuro.
    """
    cols = {}
    for nombre, (desde, hasta) in REGIMENES.items():
        d0 = pd.Timestamp(desde)
        if d0 > origen:
            continue                      # todavía no pasó: el modelo no lo ve
        d1 = pd.Timestamp(hasta) if hasta else None
        if d1 is None or d1 > origen:
            # sigue abierto en el origen -> vale de d0 en adelante, sin cierre
            cols[nombre] = (fechas >= d0).astype(float)
        else:
            cols[nombre] = ((fechas >= d0) & (fechas <= d1)).astype(float)
    return pd.DataFrame(cols, index=fechas.index)


# ─────────────────────────────────────────────────────────────────── modelos
# Todos comparten firma: (historia, horizonte, origen) -> DataFrame con
# ds/yhat/yhat_lower/yhat_upper, solo los meses futuros.

def naive_estacional(ts: pd.DataFrame, h: int, origen: pd.Timestamp) -> pd.DataFrame:
    """El mismo mes del año pasado. Es el baseline duro de cualquier serie con
    estacionalidad anual, y en delito suele ser difícil de batir."""
    fechas = pd.date_range(ts["ds"].max() + pd.offsets.MonthBegin(1), periods=h, freq="MS")
    hist = ts.set_index("ds")["y"]
    yhat = [hist.get(f - pd.DateOffset(years=1), hist.iloc[-12:].mean()) for f in fechas]
    # banda a partir del error histórico del propio naive, un año contra el otro
    err = (hist - hist.shift(12)).dropna()
    s = err.std() if len(err) > 1 else hist.std()
    return pd.DataFrame({"ds": fechas, "yhat": yhat,
                         "yhat_lower": np.array(yhat) - 1.645 * s,
                         "yhat_upper": np.array(yhat) + 1.645 * s})


def ets(ts: pd.DataFrame, h: int, origen: pd.Timestamp) -> pd.DataFrame:
    """Holt-Winters aditivo. No sabe nada de regímenes — está justamente para
    mostrar qué pasa cuando la perturbación se le mete a la tendencia."""
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    y = ts["y"].to_numpy(float)
    fit = ExponentialSmoothing(y, trend="add", seasonal="add", seasonal_periods=12).fit()
    p = np.asarray(fit.forecast(h), dtype=float)
    s = float(np.std(fit.resid))
    fechas = pd.date_range(ts["ds"].max() + pd.offsets.MonthBegin(1), periods=h, freq="MS")
    return pd.DataFrame({"ds": fechas, "yhat": np.clip(p, 0, None),
                         "yhat_lower": np.clip(p - 1.645 * s, 0, None),
                         "yhat_upper": p + 1.645 * s})


def _prophet(ts: pd.DataFrame, h: int, origen: pd.Timestamp, con_regimen: bool) -> pd.DataFrame:
    m = Prophet(yearly_seasonality=True, weekly_seasonality=False,
                daily_seasonality=False, seasonality_mode="multiplicative",
                interval_width=INTERVALO)

    entra = ts[["ds", "y"]].copy()
    futuro = pd.DataFrame({"ds": pd.date_range(
        ts["ds"].max() + pd.offsets.MonthBegin(1), periods=h, freq="MS")})
    todo = pd.concat([entra[["ds"]], futuro], ignore_index=True)

    if con_regimen:
        # multiplicativo y no aditivo porque un régimen escala el nivel: la
        # pandemia no restó 8.000 delitos, los dividió por tres
        R = regresores(todo["ds"], origen)
        for c in R.columns:
            m.add_regressor(c, mode="multiplicative")
        todo = pd.concat([todo, R], axis=1)
        entra = entra.merge(todo, on="ds", how="left")

    m.fit(entra)
    fc = m.predict(todo.iloc[len(entra):].reset_index(drop=True) if con_regimen else futuro)
    out = fc[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
    out[["yhat", "yhat_lower"]] = out[["yhat", "yhat_lower"]].clip(lower=0)
    return out


def prophet_simple(ts: pd.DataFrame, h: int, origen: pd.Timestamp) -> pd.DataFrame:
    """Prophet tal cual, el port literal de LAPD."""
    return _prophet(ts, h, origen, con_regimen=False)


def prophet_regimen(ts: pd.DataFrame, h: int, origen: pd.Timestamp) -> pd.DataFrame:
    """Prophet con las indicadoras de pandemia y del escalón de 2025."""
    return _prophet(ts, h, origen, con_regimen=True)


MODELOS = {
    "naive_estacional": naive_estacional,
    "ets": ets,
    "prophet": prophet_simple,
    "prophet_regimen": prophet_regimen,
}


# ───────────────────────────────────────────────────────────────── backtest

def etiqueta_periodo(ds: pd.Timestamp) -> str:
    """En qué régimen cae el mes objetivo. Se reporta partido porque el promedio
    global lo domina el pozo de 2020 y esconde cómo anda en años normales."""
    if pd.Timestamp("2020-03-01") <= ds <= pd.Timestamp("2022-09-01"):
        return "pandemia"
    if ds >= pd.Timestamp("2025-01-01"):
        return "quiebre 2025"
    return "normal"


def backtest(ts: pd.DataFrame) -> pd.DataFrame:
    """Origen deslizante mes a mes, horizontes 1..12."""
    filas = []
    n = len(ts)
    origenes = range(MIN_HISTORIA - 1, n - 1)      # cada origen deja ≥1 objetivo
    total = len(origenes)
    print(f"  {total} orígenes, horizonte {HORIZONTE}, {len(MODELOS)} modelos")

    for k, i in enumerate(origenes, 1):
        hist = ts.iloc[:i + 1]
        origen = hist["ds"].iloc[-1]
        h = min(HORIZONTE, n - 1 - i)
        real = ts.iloc[i + 1:i + 1 + h].set_index("ds")["y"]

        for nombre, fn in MODELOS.items():
            try:
                fc = fn(hist, h, origen).set_index("ds")
            except Exception as e:                 # ETS pide 2 ciclos completos
                print(f"    {origen.date()} {nombre}: {type(e).__name__}")
                continue
            for paso, (ds, y) in enumerate(real.items(), 1):
                if ds not in fc.index:
                    continue
                p = float(fc.loc[ds, "yhat"])
                filas.append({
                    "origen": origen, "objetivo": ds, "h": paso, "modelo": nombre,
                    "real": float(y), "pred": p, "error": p - float(y),
                    "dentro": bool(fc.loc[ds, "yhat_lower"] <= y <= fc.loc[ds, "yhat_upper"]),
                    "periodo": etiqueta_periodo(ds),
                })
        if k % 12 == 0 or k == total:
            print(f"    origen {k}/{total}  ({origen.date()})")

    return pd.DataFrame(filas)


def resumir(bt: pd.DataFrame, por: str | None = None) -> pd.DataFrame:
    llaves = ["modelo"] + ([por] if por else [])
    d = bt.assign(ae=bt["error"].abs(),
                  ape=bt["error"].abs() / bt["real"] * 100)
    r = d.groupby(llaves).agg(MAE=("ae", "mean"), MAPE=("ape", "mean"),
                              sesgo=("error", "mean"), cobertura=("dentro", "mean"),
                              n=("ae", "size")).reset_index()
    r["cobertura"] *= 100
    return r


def tabla(df: pd.DataFrame, cols: list[str], anchos: list[int]) -> None:
    print("  " + "".join(c.ljust(a) for c, a in zip(cols, anchos)))
    print("  " + "-" * sum(anchos))
    for _, r in df.iterrows():
        celdas = []
        for c, a in zip(cols, anchos):
            v = r[c]
            celdas.append((f"{v:,.1f}" if isinstance(v, float) else str(v)).ljust(a))
        print("  " + "".join(celdas))


# ─────────────────────────────────────────────────────────────────── salidas

def calibrar(bt: pd.DataFrame, modelo: str) -> pd.DataFrame:
    """Bandas empíricas por horizonte, sacadas de los errores del backtest.

    Es la misma idea que ya usa `conformal_prediction.py` en el modelo por
    hexágono —reemplazar el intervalo del modelo por cuantiles observados del
    error— pero por horizonte, porque el error a 12 meses no se parece al de 1.

    **No es el default, y conviene saber por qué.** La cobertura nativa promedia
    69,7% sobre todos los meses normales contra un 90% declarado, que a primera
    vista pide corrección. Pero abierta por año (tabla que imprime `main`) se ve
    que la sub-cobertura está entera en los orígenes con historia corta: con 3-4
    años de datos Prophet cubre 25-28%, y con 8 o más llega a 95%. O sea que hoy
    las bandas nativas ya están en su valor nominal, y calibrarlas contra los
    errores de 2019-2022 les mete adentro un problema que ya no existe: las
    ensancha hasta cubrir 98,6%. Se dejan calculadas al lado de las nativas
    porque son la evidencia de eso, y porque vuelven a ser la opción correcta si
    alguna vez se corre esto sobre una serie corta.

    Se calibra **solo sobre meses normales**: meter la pandemia o el escalón de
    2025 en los cuantiles daría bandas absurdamente anchas para todo. La
    contracara hay que decirla: la banda vale mientras 2026 sea un año normal, y
    no cubre un quiebre nuevo — ningún método que mire el pasado lo cubriría.
    """
    d = bt[(bt["modelo"] == modelo) & (bt["periodo"] == "normal")]
    a = (1 - INTERVALO) / 2
    q = d.groupby("h")["error"].quantile([a, 1 - a]).unstack()
    q.columns = ["q_bajo", "q_alto"]
    return q.reset_index()


def verificar_calibracion(bt: pd.DataFrame, corte: str = "2023-01-01") -> pd.DataFrame:
    """Cobertura de las bandas calibradas, midiendo fuera de donde se calibró.

    Si se calibrara y se midiera sobre los mismos errores, la cobertura daría
    ~90% por construcción y no diría nada. Así que los cuantiles salen de los
    orígenes anteriores a `corte` y se miden contra los posteriores.
    """
    filas = []
    for modelo in MODELOS:
        d = bt[(bt["modelo"] == modelo) & (bt["periodo"] == "normal")]
        ent, prueba = d[d["origen"] < corte], d[d["origen"] >= corte]
        if not len(ent) or not len(prueba):
            continue
        q = calibrar(bt[bt["origen"] < corte], modelo).set_index("h")
        p = prueba.join(q, on="h")
        dentro = ((p["error"] >= p["q_bajo"]) & (p["error"] <= p["q_alto"])).mean()
        filas.append({"modelo": modelo,
                      "cobertura_nativa": prueba["dentro"].mean() * 100,
                      "cobertura_calibrada": dentro * 100,
                      "n": len(prueba)})
    return pd.DataFrame(filas)


def pronostico_final(ts: pd.DataFrame, bt: pd.DataFrame | None = None) -> pd.DataFrame:
    """Los 12 meses siguientes al final de los datos, con los cuatro modelos.

    Si se pasa el backtest, agrega las bandas calibradas de cada modelo al lado
    de las nativas — se guardan las dos para que se pueda ver la diferencia.
    """
    origen = ts["ds"].max()
    out = []
    for nombre, fn in MODELOS.items():
        fc = fn(ts, HORIZONTE, origen).copy()
        fc["modelo"] = nombre
        fc["h"] = np.arange(1, len(fc) + 1)
        if bt is not None:
            q = calibrar(bt, nombre)
            fc = fc.merge(q, on="h", how="left")
            # el error se define pred − real, así que para pasar de predicción a
            # real hay que restarlo: real ≈ yhat − error
            fc["cal_lower"] = (fc["yhat"] - fc["q_alto"]).clip(lower=0)
            fc["cal_upper"] = fc["yhat"] - fc["q_bajo"]
        out.append(fc)
    return pd.concat(out, ignore_index=True)


def pronostico_por_tipo(por_tipo: pd.DataFrame) -> pd.DataFrame:
    """Mismo pronóstico abierto por tipo de delito.

    Es la apertura que más importa acá y no es decorativa: el quiebre de 2025
    movió los tipos en direcciones opuestas —robo y hurto en escalón hacia
    abajo, lesiones y amenazas en rampa hacia arriba— así que el total esconde
    dos historias distintas.
    """
    out = []
    for tipo, g in por_tipo.groupby("tipo"):
        ts = g[["ds", "y"]].sort_values("ds").reset_index(drop=True)
        if len(ts) < MIN_HISTORIA:
            continue
        fc = prophet_regimen(ts, HORIZONTE, ts["ds"].max()).copy()
        fc["tipo"] = tipo
        # referencia para leer el pronóstico: el promedio de los últimos 12 meses
        fc["prom_ult12"] = ts["y"].iloc[-12:].mean()
        out.append(fc)
    return pd.concat(out, ignore_index=True)


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    np.random.seed(SEMILLA)
    ts, por_tipo = cargar()
    print(f"\nSerie mensual: {len(ts)} meses, {ts['ds'].min().date()} a {ts['ds'].max().date()}")
    print(f"Último año: {ts['y'].iloc[-12:].mean():,.0f} delitos/mes  |  "
          f"año previo: {ts['y'].iloc[-24:-12].mean():,.0f}")

    print("\n[1] Backtest de origen deslizante...")
    bt = backtest(ts)
    bt.to_parquet(RUTA_BACKTEST, index=False)

    print(f"\n{'=' * 70}\nPRONÓSTICO MENSUAL — {bt['origen'].nunique()} orígenes, "
          f"horizontes 1-{HORIZONTE}\n{'=' * 70}")
    print("\nGlobal:")
    tabla(resumir(bt).sort_values("MAE"),
          ["modelo", "MAE", "MAPE", "sesgo", "cobertura", "n"], [18, 10, 9, 10, 12, 7])

    print("\nPor período del mes objetivo:")
    r = resumir(bt, "periodo").sort_values(["periodo", "MAE"])
    tabla(r, ["periodo", "modelo", "MAE", "MAPE", "sesgo", "cobertura"],
          [15, 18, 10, 9, 10, 12])

    print("\nSolo períodos normales, por horizonte:")
    normal = bt[bt["periodo"] == "normal"]
    rh = resumir(normal, "h").sort_values(["h", "MAE"])
    tabla(rh[rh["h"].isin([1, 3, 6, 12])],
          ["h", "modelo", "MAE", "MAPE", "sesgo", "cobertura"],
          [5, 18, 10, 9, 10, 12])

    print("\n[2] ¿Las bandas cubren lo que dicen? (nominal "
          f"{INTERVALO:.0%}, meses normales)")
    print("\n  Cobertura nativa por año del mes objetivo:")
    n = bt[bt["periodo"] == "normal"].assign(anio=bt["objetivo"].dt.year)
    cob = (n.pivot_table(index="anio", columns="modelo", values="dentro",
                         aggfunc="mean") * 100).round(1)
    print("  " + cob.to_string().replace("\n", "\n  "))
    print("\n  La sub-cobertura está en los orígenes con historia corta, no en el\n"
          "  método: con 3-4 años Prophet cubre ~26%, con 8+ llega a 95%.")
    print("\n  Calibrando con 2019-2022 y midiendo en 2023-2024:")
    tabla(verificar_calibracion(bt),
          ["modelo", "cobertura_nativa", "cobertura_calibrada", "n"],
          [18, 18, 21, 7])
    print("  -> calibrar ensancha de más. Se usa la banda nativa; la calibrada\n"
          "     queda guardada al lado, para series cortas.")

    print("\n[3] Pronóstico 2026...")
    fc = pronostico_final(ts, bt)
    fc.to_parquet(RUTA_PRONOSTICO, index=False)
    base = ts["y"].iloc[-12:].mean()
    print(f"  base (promedio 2025): {base:,.0f}/mes")
    for nombre in MODELOS:
        g = fc[fc["modelo"] == nombre]
        s = g["yhat"]
        print(f"  {nombre:18s} {s.mean():8,.0f}/mes   "
              f"({(s.mean() - base) / base:+6.1%} vs 2025)   "
              f"banda {g['yhat_lower'].mean():,.0f}-{g['yhat_upper'].mean():,.0f}   "
              f"(calibrada {g['cal_lower'].mean():,.0f}-{g['cal_upper'].mean():,.0f})")

    print("\n[4] Pronóstico 2026 por tipo (prophet_regimen)...")
    ft = pronostico_por_tipo(por_tipo)
    ft.to_parquet(RUTA_TIPOS, index=False)
    for tipo, g in ft.groupby("tipo"):
        b = g["prom_ult12"].iloc[0]
        print(f"  {tipo:12s} {g['yhat'].mean():8,.0f}/mes   "
              f"({(g['yhat'].mean() - b) / b:+6.1%} vs 2025)")

    print(f"\nGuardado: {RUTA_BACKTEST.name}, {RUTA_PRONOSTICO.name}, {RUTA_TIPOS.name}")
    print("\nRECORDATORIO: esto pronostica delito REGISTRADO. El nivel de 2025 está\n"
          "marcado como no confiable en quiebre_2025.py y esa salvedad se hereda entera.")


if __name__ == "__main__":
    main()
