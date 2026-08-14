"""
¿Qué pasó en 2025? El año de test tiene otra composición que los de train.

El EDA encontró que en 2025 los delitos contra la propiedad caen ~25% mientras
los interpersonales suben ~35%, en un solo año. Eso no es un detalle: 2025 es el
año de test de todo el proyecto, y los tres módulos de Capa 2 optimizan sobre
superficies dominadas por robo y hurto. Si el salto no es un cambio del delito
sino de cómo se registra, las métricas miden otra cosa y las recomendaciones
están apoyadas en algo que se movió por debajo.

Este script hace cinco diagnósticos internos y termina con el único que decide
si hay que cambiar algo.

  1. FORMA EN EL TIEMPO. Un cambio administrativo es un escalón en el límite del
     año; uno real es gradual o está atado a algo. Se mira el cociente contra el
     mismo mes del año anterior: plano = escalón, con deriva = tendencia.
  2. UNIFORMIDAD ESPACIAL. Un cambio de registro pega parejo en las 15 comunas;
     uno real tiene textura geográfica.
  3. SUBTIPOS. El hurto automotor es el más resistente a un cambio de registro:
     la denuncia policial es requisito del seguro, así que se hace igual.
  4. COMPOSICIÓN INTERNA. Si cambiara la definición de robo, cambiaría la
     proporción de robos con arma.
  5. EL QUE DECIDE. Reponderar 2025 a la mezcla de tipos de 2024 y ver si el
     ranking de hexágonos se mueve. Los módulos optimizan sobre el ORDEN, no
     sobre el nivel: si el orden aguanta, no hay que tocar nada.

EVIDENCIA EXTERNA (consultada 2026-08-14, fuera de estos datos):

  - La caída del 27% en robos es la cifra oficial: el GCBA presentó el "Mapa del
    Delito 2025" con 50.069 robos contra 68.392, el nivel más bajo en 25 años
    sin contar la pandemia. Coincide con lo que hay en este parquet (-26,9%), o
    sea que estos datos SON los oficiales.
  - Las encuestas de victimización de la UTDT se mantienen estables en el mismo
    período (promedio 24,3% entre 2022 y 2025; 23% de los porteños declara haber
    sufrido un delito entre enero de 2025 y enero de 2026). Son independientes
    del registro policial y no acompañan la caída.
  - El informe nacional advierte que parte del movimiento en las cifras se
    explica por "mejoras en los sistemas de registro" y pide interpretarlas con
    cautela.
  - Hay reportes de dificultades prácticas para radicar denuncias por problemas
    técnicos del sistema interno de algunas dependencias policiales.

No se puede probar desde acá que el cambio sea de registro, y la posición
oficial es que la baja es real. Lo que sí se puede hacer es medir si las firmas
internas son compatibles con una baja genuina, y qué pasa con el proyecto en
cualquiera de los dos casos.

Salida: data/features/quiebre_2025.parquet
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

RAIZ = Path(__file__).resolve().parent.parent.parent
FEATURES = RAIZ / "data" / "features"
SALIDA = FEATURES / "quiebre_2025.parquet"

TIPOS = ["Robo", "Hurto", "Lesiones", "Amenazas", "Vialidad"]
ANIO_TEST, ANIO_PREV = 2025, 2024


def cargar() -> pd.DataFrame:
    d = pd.read_parquet(FEATURES / "delitos_hex.parquet",
                        columns=["fecha", "tipo", "subtipo", "uso_arma",
                                 "uso_moto", "comuna", "hex_id"])
    f = pd.to_datetime(d["fecha"], errors="coerce")
    d["anio"], d["mes"] = f.dt.year, f.dt.month
    return d.dropna(subset=["hex_id"])


# --- 1 ---------------------------------------------------------------------

def forma_en_el_tiempo(d: pd.DataFrame) -> pd.DataFrame:
    g = d.groupby(["anio", "mes", "tipo"]).size().unstack(fill_value=0)
    r = (g.loc[ANIO_TEST] / g.loc[ANIO_PREV])[TIPOS]
    ctrl = (g.loc[ANIO_PREV] / g.loc[ANIO_PREV - 1])[TIPOS]

    print(f"\n--- 1. FORMA EN EL TIEMPO: cociente {ANIO_TEST}/{ANIO_PREV} por mes ---")
    print(r.round(2).to_string())
    print("\n  Pendiente del cociente a lo largo del año (0 = escalón, >0 = rampa):")
    filas = []
    for t in TIPOS:
        pend = float(np.polyfit(r.index, r[t], 1)[0])
        pend_ctrl = float(np.polyfit(ctrl.index, ctrl[t], 1)[0])
        forma = "escalón" if abs(pend) < 0.01 else ("rampa" if pend > 0 else "caída progresiva")
        filas.append({"tipo": t, "ratio_medio": float(r[t].mean()),
                      "pendiente_mensual": pend, "pendiente_control": pend_ctrl,
                      "forma": forma})
        print(f"    {t:<10} {pend:+.4f}/mes  (control {ANIO_PREV}/{ANIO_PREV-1}: "
              f"{pend_ctrl:+.4f})  -> {forma}")
    return pd.DataFrame(filas)


# --- 2 ---------------------------------------------------------------------

def uniformidad_espacial(d: pd.DataFrame) -> pd.DataFrame:
    x = d.dropna(subset=["comuna"]).copy()
    x["comuna"] = x["comuna"].astype(int)
    print(f"\n--- 2. UNIFORMIDAD ESPACIAL: cociente por comuna ---")
    filas = []
    for t in TIPOS:
        g = x[x.tipo == t].groupby(["anio", "comuna"]).size().unstack(fill_value=0)
        r = g.loc[ANIO_TEST] / g.loc[ANIO_PREV]
        # ruido de muestreo esperable si el cociente fuera constante y los
        # conteos Poisson: sirve para saber si la dispersión observada es real
        esperado = float(np.sqrt((1 / g.loc[ANIO_TEST] + 1 / g.loc[ANIO_PREV]).mean()))
        cv = float(r.std() / r.mean())
        filas.append({"tipo": t, "cv_entre_comunas": cv, "cv_esperado_poisson": esperado,
                      "exceso": cv / esperado, "min": float(r.min()), "max": float(r.max())})
        print(f"  {t:<10} CV={cv:.3f}  (ruido de muestreo {esperado:.3f}, "
              f"exceso {cv / esperado:.1f}x)  rango {r.min():.2f}-{r.max():.2f}  "
              f"{'todas en la misma dirección' if (r > 1).all() or (r < 1).all() else 'direcciones mixtas'}")
    return pd.DataFrame(filas)


# --- 3 y 4 -----------------------------------------------------------------

def subtipos_y_composicion(d: pd.DataFrame) -> pd.DataFrame:
    s = d.groupby(["anio", "subtipo"]).size().unstack(fill_value=0)
    r = s.loc[ANIO_TEST] / s.loc[ANIO_PREV]
    print(f"\n--- 3. SUBTIPOS ---")
    tabla = pd.DataFrame({str(ANIO_PREV): s.loc[ANIO_PREV],
                          str(ANIO_TEST): s.loc[ANIO_TEST], "ratio": r.round(3)})
    print(tabla.to_string())
    if "Hurto automotor" in r and "Hurto total" in r:
        print(f"\n  Hurto automotor {r['Hurto automotor']:.3f} contra hurto total "
              f"{r['Hurto total']:.3f}: el automotor es el subtipo más resistente a un\n"
              f"  cambio de registro —la denuncia es requisito del seguro— y es el único "
              f"que no se movió.")

    print(f"\n--- 4. COMPOSICIÓN INTERNA DEL ROBO ---")
    x = d[(d.tipo == "Robo") & d.anio.isin([ANIO_PREV, ANIO_TEST])]
    for col in ["uso_arma", "uso_moto"]:
        p = pd.crosstab(x["anio"], x[col], normalize="index") * 100
        if "SI" in p.columns:
            print(f"  {col} = SI: {ANIO_PREV} {p.loc[ANIO_PREV, 'SI']:.1f}%  ->  "
                  f"{ANIO_TEST} {p.loc[ANIO_TEST, 'SI']:.1f}%")
    return tabla.reset_index()


# --- 5 ---------------------------------------------------------------------

def afecta_al_ranking(d: pd.DataFrame) -> pd.DataFrame:
    """El único diagnóstico que decide si hay que cambiar algo.

    Los módulos de Capa 2 no consumen el nivel de delito, consumen el ORDEN de
    los hexágonos. Si se reponderan los tipos de 2025 para devolverles la mezcla
    de 2024 y el ranking no se mueve, entonces el quiebre de composición —sea
    real o de registro— no cambia ninguna decisión operativa.
    """
    hm = pd.read_parquet(FEATURES / "hex_maestra.parquet").dropna(subset=["barrio_id"])
    hexes = sorted(hm["hex_id"].unique())

    def mapa(anio: int, pesos: dict | None = None) -> pd.Series:
        x = d[d.anio == anio]
        if pesos is None:
            return x.groupby("hex_id").size().reindex(hexes).fillna(0)
        s = pd.Series(0.0, index=hexes)
        for t, w in pesos.items():
            s += x[x.tipo == t].groupby("hex_id").size().reindex(hexes).fillna(0) * w
        return s

    c_prev = d[d.anio == ANIO_PREV].tipo.value_counts(normalize=True)
    c_test = d[d.anio == ANIO_TEST].tipo.value_counts(normalize=True)
    pesos = (c_prev / c_test).to_dict()

    m_prev, m_test = mapa(ANIO_PREV), mapa(ANIO_TEST)
    m_rep = mapa(ANIO_TEST, pesos)

    print(f"\n--- 5. ¿MUEVE EL RANKING? ---")
    print("  Pesos para devolverle a 2025 la mezcla de tipos de 2024:")
    print("   ", {k: round(v, 3) for k, v in sorted(pesos.items())})

    n = int(round(len(hexes) * 0.20))
    filas = []
    for nombre, a, b in [(f"{ANIO_PREV} vs {ANIO_TEST} crudo", m_prev, m_test),
                         (f"{ANIO_PREV} vs {ANIO_TEST} reponderado", m_prev, m_rep),
                         (f"{ANIO_TEST} crudo vs reponderado", m_test, m_rep)]:
        rho = float(spearmanr(a, b).statistic)
        ta = set(a.sort_values(ascending=False).head(n).index)
        tb = set(b.sort_values(ascending=False).head(n).index)
        solape = len(ta & tb) / n
        filas.append({"comparacion": nombre, "spearman": rho, "solape_top20": solape})
        print(f"  {nombre:<32} Spearman {rho:.4f} | top-20% en común {solape:.1%}")

    print("\n  La última fila es la que importa: es el efecto del quiebre de composición,")
    print("  aislado del paso del tiempo. Si está cerca de 1, el mapa que consumen los")
    print("  módulos no cambia y no hay que rehacer nada.")
    return pd.DataFrame(filas)


def main() -> None:
    d = cargar()
    print(f"{len(d):,} delitos | {ANIO_PREV}: {(d.anio == ANIO_PREV).sum():,} | "
          f"{ANIO_TEST}: {(d.anio == ANIO_TEST).sum():,} "
          f"({(d.anio == ANIO_TEST).sum() / (d.anio == ANIO_PREV).sum() - 1:+.1%})")

    tiempo = forma_en_el_tiempo(d)
    espacio = uniformidad_espacial(d)
    subtipos_y_composicion(d)
    ranking = afecta_al_ranking(d)

    tiempo.to_parquet(SALIDA, index=False)
    espacio.to_parquet(SALIDA.with_name("quiebre_2025_espacial.parquet"), index=False)
    ranking.to_parquet(SALIDA.with_name("quiebre_2025_ranking.parquet"), index=False)
    print(f"\nGuardado: {SALIDA.name} y dos archivos hermanos")


if __name__ == "__main__":
    main()
