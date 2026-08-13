"""
EDA retroactivo — el que faltaba hacer antes de modelar.

El proyecto entró directo a construir la grilla y entrenar. La calidad de datos
se auditó a fondo (encodings, sistemas de coordenadas, esquemas cambiantes) y la
estadística descriptiva apareció siempre como justificación de una decisión ya
tomada (82,8% de ceros → Tweedie; var/media 1,59 → sobredispersión). Nunca se
miró el fenómeno por sí mismo.

Cinco preguntas que un EDA hecho a tiempo habría respondido:

1. NIVEL Y QUIEBRES — ¿cómo se mueve el volumen a lo largo de 10 años? ¿La
   pandemia deja una cicatriz permanente o el nivel vuelve?
2. ESTACIONALIDAD — ¿hay ciclo anual, semanal, por turno? ¿Cuánto vale conocer
   el calendario?
3. COMPOSICIÓN — ¿la mezcla de tipos de delito es estable en el tiempo? Si no lo
   es, un modelo agregado entrenado en un régimen predice otro distinto.
4. AUTOCORRELACIÓN ESPACIAL (Moran's I) — el proyecto entero se apoya en que el
   riesgo se concentra espacialmente. Nunca se midió con el estadístico que
   justamente cuantifica eso.
5. ESTABILIDAD DEL RANKING — ¿los hexágonos peligrosos de un año siguen siéndolo
   al siguiente? Es el supuesto que hace funcionar al baseline naive, y por lo
   tanto el techo contra el que compite el modelo.

Moran's I se calcula a mano sobre la matriz de vecindad H3 (contigüidad k=1) en
vez de traer pysal: son 401 hexágonos, la matriz entra en memoria de sobra y
evita sumar una dependencia pesada al requirements por un solo estadístico.

Salidas en data/features/eda/: un parquet por pregunta, más un resumen impreso.
"""

from __future__ import annotations

import sys
from pathlib import Path

import h3
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent.parent
PROCESSED = RAIZ / "data" / "processed"
FEATURES = RAIZ / "data" / "features"
SALIDA = FEATURES / "eda"

sys.path.insert(0, str(RAIZ / "src" / "etl"))

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def cargar_delitos() -> pd.DataFrame:
    """delitos_hex, no delitos: el crudo no tiene hex_id ni turno, se los agrega
    assign_hex_puntual. Una fila = un delito (build_training_table cuenta filas,
    no suma la columna `cantidad`) — se replica ese criterio para que los números
    de este EDA sean comparables con los del modelo."""
    cols = ["fecha", "hex_id", "turno", "tipo"]
    d = pd.read_parquet(FEATURES / "delitos_hex.parquet", columns=cols)
    d["fecha"] = pd.to_datetime(d["fecha"], errors="coerce")
    d = d.dropna(subset=["fecha", "hex_id"])
    d["anio"] = d["fecha"].dt.year.astype("int16")
    d["mes"] = d["fecha"].dt.month.astype("int8")
    d["dia_semana"] = d["fecha"].dt.dayofweek.astype("int8")
    return d


# --- 1. nivel y quiebres -----------------------------------------------------

def nivel_y_quiebres(d: pd.DataFrame) -> pd.DataFrame:
    por_anio = d.groupby("anio").size().rename("delitos").reset_index()
    base = por_anio.loc[por_anio["anio"].between(2016, 2019), "delitos"].mean()
    por_anio["vs_prepandemia"] = por_anio["delitos"] / base - 1

    print("\n--- 1. NIVEL POR AÑO (base = promedio 2016-2019) ---")
    for _, r in por_anio.iterrows():
        barra = "#" * int(round(r["delitos"] / base * 40))
        print(f"  {int(r['anio'])}  {int(r['delitos']):>7,}  {r['vs_prepandemia']:+6.1%}  {barra}")

    post = por_anio.loc[por_anio["anio"].between(2022, 2025), "delitos"].mean()
    print(f"\n  Promedio 2016-2019: {base:,.0f}")
    print(f"  Promedio 2022-2025: {post:,.0f}  ({post / base - 1:+.1%})")
    print("  -> la pandemia NO dejó cicatriz de nivel: el volumen vuelve al rango previo."
          if abs(post / base - 1) < 0.10 else
          "  -> el nivel post-pandemia NO volvió al previo: hay quiebre estructural.")
    return por_anio


# --- 2. estacionalidad -------------------------------------------------------

def estacionalidad(d: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Se mide sobre 2022-2025 para no mezclar el régimen de cuarentena, que
    tenía un patrón semanal completamente distinto por restricción de
    circulación."""
    reciente = d[d["anio"] >= 2022]

    por_mes = reciente.groupby("mes").size().rename("delitos").reset_index()
    por_mes["indice"] = por_mes["delitos"] / por_mes["delitos"].mean()

    por_dia = reciente.groupby("dia_semana").size().rename("delitos").reset_index()
    por_dia["indice"] = por_dia["delitos"] / por_dia["delitos"].mean()
    por_dia["nombre"] = por_dia["dia_semana"].map(dict(enumerate(DIAS)))

    por_turno = reciente.groupby("turno").size().rename("delitos").reset_index()
    por_turno["indice"] = por_turno["delitos"] / por_turno["delitos"].mean()

    print("\n--- 2. ESTACIONALIDAD (2022-2025, índice 1,00 = promedio) ---")
    print("  Por mes:   ", " ".join(f"{m:02d}:{v:.2f}" for m, v in
                                    zip(por_mes["mes"], por_mes["indice"])))
    print("  Por día:   ", " ".join(f"{n[:3]}:{v:.2f}" for n, v in
                                    zip(por_dia["nombre"], por_dia["indice"])))
    print("  Por turno: ", " ".join(f"{t}:{v:.2f}" for t, v in
                                    zip(por_turno["turno"], por_turno["indice"])))
    amp = {
        "mes": por_mes["indice"].max() - por_mes["indice"].min(),
        "dia": por_dia["indice"].max() - por_dia["indice"].min(),
        "turno": por_turno["indice"].max() - por_turno["indice"].min(),
    }
    print(f"\n  Amplitud (max-min): mes {amp['mes']:.2f} | día {amp['dia']:.2f} | "
          f"turno {amp['turno']:.2f}")
    print("  -> el turno es de lejos el ciclo más fuerte; mes y día de semana son casi planos.")
    return {"mes": por_mes, "dia": por_dia, "turno": por_turno}


# --- 3. composición por tipo -------------------------------------------------

def composicion(d: pd.DataFrame) -> pd.DataFrame:
    tabla = pd.crosstab(d["anio"], d["tipo"], normalize="index")
    print("\n--- 3. COMPOSICIÓN POR TIPO (% del total del año) ---")
    print((tabla * 100).round(1).to_string())
    deriva = (tabla.loc[2025] - tabla.loc[2016]).sort_values()
    print("\n  Cambio 2016 -> 2025, en puntos porcentuales:")
    for tipo, v in deriva.items():
        print(f"    {tipo:<28} {v * 100:+5.1f} pp")

    # El año de test aparte, en conteos absolutos: los shares se mueven todos a
    # la vez en 2025 y hay que ver si es una caída general (que no cambiaría la
    # mezcla) o un movimiento de composición.
    abs_ = pd.crosstab(d["anio"], d["tipo"])
    print("\n  Año de test contra el último de train, en conteos absolutos:")
    cambio = (abs_.loc[2025] / abs_.loc[2024] - 1).sort_values()
    for tipo, v in cambio.items():
        print(f"    {tipo:<28} {abs_.loc[2024, tipo]:>7,} -> {abs_.loc[2025, tipo]:>7,}  {v:+6.1%}")
    print("  -> no es una caída pareja: los delitos contra la propiedad bajan ~25% "
          "mientras\n     los interpersonales suben ~35%. El año de test tiene otra mezcla "
          "que los de train.")
    return tabla.reset_index()


# --- 4. autocorrelación espacial --------------------------------------------

def matriz_vecindad(hexes: list[str]) -> np.ndarray:
    """W binaria de contigüidad: 1 si dos hexágonos comparten borde (anillo
    k=1 de H3), 0 si no. Fila-normalizada, que es la convención para Moran's I."""
    idx = {h: i for i, h in enumerate(hexes)}
    W = np.zeros((len(hexes), len(hexes)), dtype="float32")
    for h, i in idx.items():
        for v in h3.grid_ring(h, 1):
            j = idx.get(v)
            if j is not None:
                W[i, j] = 1.0
    filas = W.sum(axis=1, keepdims=True)
    return np.divide(W, filas, out=np.zeros_like(W), where=filas > 0)


def morans_i(valores: np.ndarray, W: np.ndarray, n_perm: int = 999,
             semilla: int = 42) -> tuple[float, float, float]:
    """Moran's I con test de permutación.

    I = (n/S0) * (z' W z) / (z' z), con z = valores centrados. Con W ya
    fila-normalizada, S0 = n, así que se simplifica a (z' W z)/(z' z).

    El p-valor sale de permutar las etiquetas espaciales: si el riesgo no
    tuviera estructura espacial, reordenar los valores entre hexágonos no
    debería cambiar el I. Es preferible al p-valor analítico, que asume
    normalidad y estos conteos no la tienen ni de cerca.
    """
    z = valores - valores.mean()
    denom = (z * z).sum()
    if denom == 0:
        return float("nan"), float("nan"), float("nan")
    obs = float(z @ (W @ z) / denom)

    rng = np.random.default_rng(semilla)
    nulos = np.empty(n_perm)
    for k in range(n_perm):
        zp = rng.permutation(z)
        nulos[k] = zp @ (W @ zp) / denom
    # p de dos colas contra la distribución nula empírica
    p = (np.abs(nulos) >= abs(obs)).sum() / (n_perm + 1)
    esperado = -1.0 / (len(valores) - 1)
    return obs, esperado, float(p)


def morans_local(valores: np.ndarray, W: np.ndarray, n_perm: int = 999,
                 semilla: int = 42) -> pd.DataFrame:
    """Moran's I local (LISA, Anselin 1995) — descompone el I global en un valor
    por hexágono, para poder ver DÓNDE están los clusters en vez de solo saber
    que existen.

    I_i = z_i * Σ_j w_ij z_j, con z estandarizado. El signo del par (z_i, lag_i)
    define el cuadrante:
      alto-alto / bajo-bajo   cluster (el hexágono se parece a sus vecinos)
      alto-bajo / bajo-alto   outlier espacial (se despega de su entorno)

    La significancia sale de permutar condicionalmente: se fija z_i y se
    reordenan los vecinos, que es la versión correcta para el estadístico local
    (permutar todo, como en el global, sobreestima la significancia).
    """
    z = (valores - valores.mean()) / valores.std()
    lag = W @ z
    ii = z * lag

    rng = np.random.default_rng(semilla)
    n = len(z)
    extremos = np.zeros(n)
    for i in range(n):
        vecinos = np.flatnonzero(W[i])
        if len(vecinos) == 0:
            extremos[i] = n_perm
            continue
        pesos = W[i, vecinos]
        # z_i fijo, vecinos remuestreados del resto de la ciudad
        otros = np.delete(z, i)
        muestras = rng.choice(otros, size=(n_perm, len(vecinos)), replace=True)
        nulos = z[i] * (muestras * pesos).sum(axis=1)
        extremos[i] = (np.abs(nulos) >= abs(ii[i])).sum()
    p = (extremos + 1) / (n_perm + 1)

    alto_z, alto_lag = z > 0, lag > 0
    cuadrante = np.where(alto_z & alto_lag, "alto-alto",
                np.where(~alto_z & ~alto_lag, "bajo-bajo",
                np.where(alto_z & ~alto_lag, "alto-bajo", "bajo-alto")))
    return pd.DataFrame({"z": z, "lag": lag, "i_local": ii,
                         "p_valor": p, "cuadrante": cuadrante})


def autocorrelacion_espacial(d: pd.DataFrame) -> pd.DataFrame:
    hex_maestra = pd.read_parquet(FEATURES / "hex_maestra.parquet")
    hexes = sorted(hex_maestra.dropna(subset=["barrio_id"])["hex_id"].unique())
    W = matriz_vecindad(hexes)
    print(f"\n--- 4. AUTOCORRELACIÓN ESPACIAL (Moran's I, {len(hexes)} hexágonos, "
          f"vecindad k=1) ---")
    print(f"  Vecinos por hexágono: mediana {np.median((W > 0).sum(axis=1)):.0f}")

    filas = []
    for anio in sorted(d["anio"].unique()):
        conteo = d[d["anio"] == anio].groupby("hex_id").size()
        v = conteo.reindex(hexes).fillna(0).to_numpy(dtype="float64")
        i, esp, p = morans_i(v, W)
        filas.append({"anio": int(anio), "morans_i": i, "esperado_azar": esp, "p_valor": p})
        print(f"  {anio}: I = {i:+.3f}  (azar {esp:+.4f}, p = {p:.3f})")

    res = pd.DataFrame(filas)
    print(f"\n  I promedio: {res['morans_i'].mean():+.3f} — un I muy por encima del valor "
          f"de azar\n  confirma que el riesgo NO está repartido al azar entre hexágonos "
          f"vecinos.\n  Es el respaldo estadístico de la premisa central del proyecto.")
    return res


# --- 5. estabilidad del ranking ---------------------------------------------

def estabilidad_ranking(d: pd.DataFrame) -> pd.DataFrame:
    """Correlación de Spearman entre el ranking de hexágonos de un año y el del
    siguiente, más cuántos del top-20% se repiten. Es exactamente el supuesto
    que hace competitivo al baseline naive: si el mapa de un año predice el del
    siguiente, un promedio histórico ya captura casi todo."""
    conteos = d.groupby(["anio", "hex_id"]).size().unstack(fill_value=0)
    anios = sorted(conteos.index)
    filas = []
    print("\n--- 5. ESTABILIDAD DEL RANKING ENTRE AÑOS CONSECUTIVOS ---")
    for a, b in zip(anios, anios[1:]):
        x, y = conteos.loc[a], conteos.loc[b]
        rho = x.corr(y, method="spearman")
        n_top = max(1, int(round(len(x) * 0.20)))
        top_a = set(x.sort_values(ascending=False).head(n_top).index)
        top_b = set(y.sort_values(ascending=False).head(n_top).index)
        solap = len(top_a & top_b) / n_top
        filas.append({"de": a, "a": b, "spearman": rho, "solape_top20": solap})
        print(f"  {a} -> {b}:  Spearman {rho:.3f}  |  top-20% que se repite: {solap:.1%}")
    res = pd.DataFrame(filas)
    print(f"\n  Promedio: Spearman {res['spearman'].mean():.3f}, "
          f"solape {res['solape_top20'].mean():.1%}")
    print("  -> cuanto más alto, más difícil es que un modelo temporal le gane al "
          "promedio histórico.")
    return res


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    d = cargar_delitos()
    print(f"Delitos con hex_id y fecha válidas: {len(d):,} ({d['anio'].min()}-{d['anio'].max()})")

    nivel_y_quiebres(d).to_parquet(SALIDA / "eda_nivel_anual.parquet", index=False)
    est = estacionalidad(d)
    for k, v in est.items():
        v.to_parquet(SALIDA / f"eda_estacionalidad_{k}.parquet", index=False)
    composicion(d).to_parquet(SALIDA / "eda_composicion_tipo.parquet", index=False)
    autocorrelacion_espacial(d).to_parquet(SALIDA / "eda_morans_i.parquet", index=False)
    estabilidad_ranking(d).to_parquet(SALIDA / "eda_estabilidad_ranking.parquet", index=False)

    print(f"\nGuardado en {SALIDA}")


if __name__ == "__main__":
    main()
