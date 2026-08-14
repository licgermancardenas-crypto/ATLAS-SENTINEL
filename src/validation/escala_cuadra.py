"""
¿El techo del proyecto es del fenómeno o de la resolución? (hipótesis de Weisburd)

El EDA midió que el ranking de hexágonos de 700m es casi inmóvil entre años
(Spearman 0,983) y de ahí salió la conclusión de que el problema de priorización
espacial está saturado. Pero eso se midió a UNA resolución. La "ley de
concentración del delito" (Weisburd 2015) dice que el delito no se concentra en
barrios sino en **segmentos de calle**: que un puñado de cuadras explica la
mitad de los casos, y que esas cuadras sí se prenden y apagan.

Si eso vale acá, adentro de un hexágono peligroso habría dos cuadras que cargan
todo y el resto tranquilo, con dinámica real que la grilla de 700m promedia y
esconde. Sería la única puerta abierta del lado del modelado — y no es cambiar
de algoritmo, es cambiar de unidad de análisis.

Tres preguntas:

  1. CONCENTRACIÓN. ¿Qué fracción de las cuadras acumula el 25% y el 50% de los
     delitos? Weisburd reporta ~5% de segmentos para el 50% en varias ciudades.
  2. ESTABILIDAD. ¿El ranking de cuadras se mueve más entre años que el de
     hexágonos? Esta es la que decide.
  3. ADENTRO DEL HEXÁGONO. En los hexágonos calientes, ¿el delito está repartido
     o concentrado en pocas cuadras? Es lo que diría si conviene desplegar por
     zona o por punto.

EL CONTROL QUE HACE FALTA. Comparar la estabilidad de cuadras contra la de
hexágonos sin más sería trampa: cada cuadra tiene ~4 delitos por año contra ~330
de un hexágono, y con conteos chicos el ranking se desordena solo por ruido de
muestreo, sin que el fenómeno haya cambiado. Así que la estabilidad observada se
compara contra una **nula de Poisson**: se simulan dos años con la tasa de cada
unidad FIJA y se mide qué Spearman da el ruido por sí solo. Si lo observado se
parece a la nula, la unidad es tan estable como los datos permiten ver y no hay
dinámica que aprovechar. Si es bastante menor, hay movimiento real.

LIMITACIÓN DE LOS DATOS, medida acá mismo: 8,4% de los delitos caen en 564
coordenadas repetidas, y las más pobladas están en Villa Lugano y Barracas —
zonas de urbanización informal donde la dirección no geocodifica y el sistema
cae a un punto único. Asignados a una cuadra la inflarían sola. Todo se calcula
dos veces, con y sin esos puntos.

Salida: data/features/escala_cuadra.parquet
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd
from scipy.stats import spearmanr
from shapely import STRtree
from shapely.geometry import LineString

RAIZ = Path(__file__).resolve().parent.parent.parent
FEATURES = RAIZ / "data" / "features"
SALIDA = FEATURES / "escala_cuadra.parquet"

CRS_GEO, CRS_METROS = "EPSG:4326", "EPSG:5347"
CORTE_PUNTO_SOSPECHOSO = 100    # delitos en una misma coordenada exacta
SEMILLA = 42


# ------------------------------------------------------------------ datos

def cargar_delitos() -> pd.DataFrame:
    d = pd.read_parquet(FEATURES / "delitos_hex.parquet",
                        columns=["fecha", "latitud", "longitud", "hex_id"])
    d["anio"] = pd.to_datetime(d["fecha"], errors="coerce").dt.year
    d = d.dropna(subset=["latitud", "longitud", "anio", "hex_id"])
    d = d[d["latitud"].between(-34.75, -34.50) & d["longitud"].between(-58.55, -58.30)]

    # marca de punto sospechoso de relleno del geocodificador
    n_por_punto = d.groupby(["latitud", "longitud"])["anio"].transform("size")
    d["punto_sospechoso"] = n_por_punto >= CORTE_PUNTO_SOSPECHOSO
    print(f"{len(d):,} delitos georreferenciados | "
          f"{d['punto_sospechoso'].sum():,} ({d['punto_sospechoso'].mean():.1%}) "
          f"en coordenadas con {CORTE_PUNTO_SOSPECHOSO}+ repeticiones")
    return d


def cargar_segmentos() -> gpd.GeoSeries:
    """Los 37.036 tramos del grafo vial de OSM, el mismo que usan los módulos."""
    G = ox.io.load_graphml(FEATURES / "grafo_vial.graphml")
    geoms = []
    for u, v, dd in G.edges(data=True):
        g = dd.get("geometry")
        if g is None:
            g = LineString([(G.nodes[u]["x"], G.nodes[u]["y"]),
                            (G.nodes[v]["x"], G.nodes[v]["y"])])
        geoms.append(g)
    s = gpd.GeoSeries(geoms, crs=CRS_GEO).to_crs(CRS_METROS)
    print(f"{len(s):,} segmentos de calle | largo mediano {s.length.median():.0f} m")
    return s


def asignar_segmento(d: pd.DataFrame, segmentos: gpd.GeoSeries) -> np.ndarray:
    pts = gpd.GeoSeries(gpd.points_from_xy(d["longitud"], d["latitud"]),
                        crs=CRS_GEO).to_crs(CRS_METROS)
    arbol = STRtree(segmentos.to_numpy())
    salida = np.empty(len(d), dtype="int32")
    paso = 100_000
    arr = pts.to_numpy()
    for i in range(0, len(arr), paso):
        salida[i:i + paso] = arbol.nearest(arr[i:i + paso])
    return salida


# ------------------------------------------------------------------ 1

def concentracion(conteo: np.ndarray, etiqueta: str) -> dict:
    """Curva de Lorenz del delito: qué fracción de unidades acumula qué fracción
    de los casos. Se cuentan TODAS las unidades, también las que nunca tuvieron
    un delito — si no, la concentración sale inflada por construcción."""
    orden = np.sort(conteo)[::-1]
    acum = np.cumsum(orden) / orden.sum()
    res = {"unidad": etiqueta, "n_unidades": len(conteo),
           "pct_sin_delitos": float((conteo == 0).mean())}
    for objetivo in (0.25, 0.50):
        k = int(np.searchsorted(acum, objetivo)) + 1
        res[f"pct_unidades_para_{int(objetivo * 100)}"] = k / len(conteo)
    for pct in (0.01, 0.05):
        k = max(1, int(round(len(conteo) * pct)))
        res[f"pct_delitos_en_top_{int(pct * 100)}"] = float(acum[k - 1])
    return res


# ------------------------------------------------------------------ 2

def estabilidad_contra_nula(m: np.ndarray, etiqueta: str,
                            n_sim: int = 40) -> dict:
    """m: unidades × años. Compara la estabilidad observada entre años
    consecutivos contra la que daría el puro ruido de muestreo si la tasa de
    cada unidad fuera constante en el tiempo."""
    rng = np.random.default_rng(SEMILLA)
    obs, nulos = [], []
    tasa = m.mean(axis=1)

    for j in range(m.shape[1] - 1):
        a, b = m[:, j], m[:, j + 1]
        obs.append(spearmanr(a, b).statistic)
        # nula: dos años independientes con la MISMA tasa por unidad, escalada
        # al total de cada año para no mezclar el efecto de nivel
        for _ in range(n_sim // (m.shape[1] - 1) + 1):
            sa = rng.poisson(tasa * a.sum() / tasa.sum())
            sb = rng.poisson(tasa * b.sum() / tasa.sum())
            nulos.append(spearmanr(sa, sb).statistic)

    obs, nulos = np.array(obs), np.array(nulos)
    return {"unidad": etiqueta, "spearman_observado": float(obs.mean()),
            "spearman_nula_poisson": float(nulos.mean()),
            "brecha": float(nulos.mean() - obs.mean()),
            "delitos_por_unidad_por_anio": float(m.mean())}


def matriz_por_anio(claves: np.ndarray, anios: np.ndarray,
                    n_unidades: int, lista_anios: list[int]) -> np.ndarray:
    m = np.zeros((n_unidades, len(lista_anios)), dtype="float64")
    idx = {a: i for i, a in enumerate(lista_anios)}
    col = np.array([idx[a] for a in anios])
    np.add.at(m, (claves, col), 1.0)
    return m


# ------------------------------------------------------------------ 3

def dentro_del_hexagono(d: pd.DataFrame) -> pd.DataFrame:
    """En los hexágonos más calientes, ¿cuánto del delito cae en sus pocas
    cuadras top? Es la pregunta operativa: si está repartido, desplegar por zona
    es correcto; si está concentrado, se está regando de más."""
    calientes = d.groupby("hex_id").size().sort_values(ascending=False).head(40).index
    filas = []
    for h in calientes:
        c = d[d.hex_id == h].groupby("segmento").size().sort_values(ascending=False)
        total = c.sum()
        filas.append({"hex_id": h, "delitos": int(total),
                      "segmentos_con_delito": len(c),
                      "pct_en_top3": float(c.head(3).sum() / total),
                      "pct_en_top5": float(c.head(5).sum() / total)})
    return pd.DataFrame(filas)


# ------------------------------------------------------------------ main

def analizar(d: pd.DataFrame, n_seg: int, etiqueta: str) -> tuple[list, list]:
    anios = sorted(d["anio"].astype(int).unique())
    hexes = sorted(d["hex_id"].unique())
    idx_hex = {h: i for i, h in enumerate(hexes)}

    m_seg = matriz_por_anio(d["segmento"].to_numpy(), d["anio"].astype(int).to_numpy(),
                            n_seg, anios)
    m_hex = matriz_por_anio(d["hex_id"].map(idx_hex).to_numpy(),
                            d["anio"].astype(int).to_numpy(), len(hexes), anios)

    conc = [concentracion(m_seg.sum(axis=1), f"cuadra ({etiqueta})"),
            concentracion(m_hex.sum(axis=1), f"hexágono ({etiqueta})")]
    est = [estabilidad_contra_nula(m_seg, f"cuadra ({etiqueta})"),
           estabilidad_contra_nula(m_hex, f"hexágono ({etiqueta})")]
    return conc, est


def main() -> None:
    d = cargar_delitos()
    segmentos = cargar_segmentos()
    print("\nAsignando cada delito a su cuadra más cercana...")
    d["segmento"] = asignar_segmento(d, segmentos)

    conc, est = analizar(d, len(segmentos), "todos")
    limpio = d[~d["punto_sospechoso"]]
    conc2, est2 = analizar(limpio, len(segmentos), "sin puntos sospechosos")

    tc = pd.DataFrame(conc + conc2)
    print("\n--- 1. CONCENTRACIÓN ---")
    print(tc.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    te = pd.DataFrame(est + est2)
    print("\n--- 2. ESTABILIDAD DEL RANKING, CONTRA LA NULA DE POISSON ---")
    print(te.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print("\n  'brecha' = cuánto peor es la estabilidad real que la que daría el ruido solo.")
    print("  Cerca de 0 -> la unidad es tan estable como los datos dejan ver: no hay")
    print("  dinámica aprovechable. Grande -> hay movimiento real que valdría modelar.")

    td = dentro_del_hexagono(d)
    print("\n--- 3. ADENTRO DE LOS 40 HEXÁGONOS MÁS CALIENTES ---")
    print(f"  Segmentos con delito por hexágono: mediana {td.segmentos_con_delito.median():.0f}")
    print(f"  Delito en las 3 peores cuadras:    mediana {td.pct_en_top3.median():.1%}")
    print(f"  Delito en las 5 peores cuadras:    mediana {td.pct_en_top5.median():.1%}")

    tc.to_parquet(SALIDA, index=False)
    te.to_parquet(SALIDA.with_name("escala_cuadra_estabilidad.parquet"), index=False)
    td.to_parquet(SALIDA.with_name("escala_cuadra_dentro_hex.parquet"), index=False)
    print(f"\nGuardado: {SALIDA.name} y dos archivos hermanos")


if __name__ == "__main__":
    main()
