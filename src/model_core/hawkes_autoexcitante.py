"""
¿Hay contagio near-repeat en el delito de CABA, y sirve para predecir?

La única familia de modelos que el proyecto nunca tocó. Todo lo entrenado hasta
acá es LightGBM: catorce modelos, un solo algoritmo. La ausencia que pesa no es
"no probamos random forest" —daría lo mismo— sino los **procesos de punto
auto-excitantes** (Hawkes/ETAS), que son la familia canónica del pronóstico de
delito desde Mohler et al. 2011 y la base de PredPol.

La diferencia es conceptual, no de capacidad. LightGBM ve lags y rollings: sabe
*que* hubo delitos cerca hace poco, pero tiene que aprender la forma del efecto
desde cero, con features que alguien eligió a mano. Un Hawkes **impone** la
estructura: cada delito eleva la probabilidad de otro delito cerca en el tiempo
y en el espacio, con un decaimiento que se estima. Es exactamente la hipótesis
near-repeat, y es la única que el modelo actual no puede representar.

FORMULACIÓN — Hawkes en tiempo discreto sobre la grilla hexágono × día:

    λ_i(t) = μ_i  +  θ0·A_i(t)  +  θ1·Σ_{j∈anillo1(i)} A_j(t)  +  θ2·Σ_{j∈anillo2(i)} A_j(t)

    A_i(t) = φ·A_i(t-1) + (1-φ)·N_i(t-1)          φ = exp(-1/τ)

A es la actividad reciente del hexágono con núcleo geométrico normalizado: cada
delito pasado aporta peso total 1 repartido en el tiempo, así que θ_k se lee
directo como "cuántos delitos hijos genera un delito, en cada hexágono a
distancia k". El **cociente de ramificación** n = θ0 + 6·θ1 + 12·θ2 es la
fracción de delitos que el modelo atribuye a contagio en vez de a fondo: n=0 es
"no hay near-repeat", n→1 es "casi todo es contagio".

Grano hexágono × DÍA, no × turno: el near-repeat es un fenómeno de escala diaria
y el EDA mostró que el ciclo de turno es una constante multiplicativa por celda
(amplitud 1,35, estable), o sea que separar turnos acá agregaría parámetros sin
agregar hipótesis. μ_i constante por hexágono por la misma razón: el EDA midió
amplitudes de 0,13 por mes y 0,21 por día de semana, casi planas.

AJUSTE: λ es lineal en (μ, θ) dado τ, y la log-verosimilitud de Poisson es
cóncava ahí, así que el ajuste de los 404 parámetros es convexo — se hace con
L-BFGS-B y gradiente analítico. τ, que entra no lineal, se recorre por grilla y
se elige por verosimilitud en validación (2024). Test es 2025, igual que todo el
resto del proyecto.

Se compara contra el promedio histórico por hexágono y contra el LightGBM de
producción agregado al mismo grano, para que las tres columnas sean el mismo
número medido sobre las mismas filas.

Salida: data/features/hawkes_resultados.parquet
"""

from __future__ import annotations

import gc
import sys
from pathlib import Path

import h3
import numpy as np
import pandas as pd
from scipy.optimize import minimize

RAIZ = Path(__file__).resolve().parent.parent.parent
FEATURES = RAIZ / "data" / "features"
SALIDA = FEATURES / "hawkes_resultados.parquet"

sys.path.insert(0, str(RAIZ / "src" / "model_core"))

# Escala de decaimiento del núcleo, en días. Llega hasta un año a propósito: si
# la verosimilitud sigue mejorando con memorias larguísimas, el término
# "auto-excitante" no está capturando contagio near-repeat (que dura días) sino
# funcionando como un estimador adaptativo del nivel local. Distinguir esas dos
# cosas es toda la pregunta.
TAUS = [0.5, 1, 2, 3, 5, 7, 14, 30, 60, 90, 180, 365]
TAU_LENTO = 180        # el término de deriva lenta del modelo de dos escalas
TAUS_RAPIDOS = [1, 2, 3, 5, 7]
KS = [0.10, 0.20, 0.30]
EPS = 1e-9


# ------------------------------------------------------------------ datos

def cargar_matriz() -> tuple[np.ndarray, list[str], pd.DatetimeIndex]:
    """Conteo de delitos por hexágono × día. 401 × 3.653, sumando los 4 turnos."""
    d = pd.read_parquet(FEATURES / "delitos_hex.parquet", columns=["fecha", "hex_id"])
    d["fecha"] = pd.to_datetime(d["fecha"], errors="coerce").dt.normalize()
    d = d.dropna(subset=["fecha", "hex_id"])

    hm = pd.read_parquet(FEATURES / "hex_maestra.parquet").dropna(subset=["barrio_id"])
    hexes = sorted(hm["hex_id"].unique())
    idx_hex = {h: i for i, h in enumerate(hexes)}

    fechas = pd.date_range(d["fecha"].min(), d["fecha"].max(), freq="D")
    idx_fecha = {f: i for i, f in enumerate(fechas)}

    N = np.zeros((len(hexes), len(fechas)), dtype="float32")
    fi = d["fecha"].map(idx_fecha).to_numpy()
    hi = d["hex_id"].map(idx_hex).to_numpy()
    ok = ~pd.isna(hi)
    np.add.at(N, (hi[ok].astype(int), fi[ok].astype(int)), 1.0)
    return N, hexes, fechas


def matrices_anillo(hexes: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Adyacencia binaria de los anillos H3 k=1 y k=2, recortada a los hexágonos
    de la grilla (los de borde tienen menos vecinos y eso está bien: el contagio
    que se iría fuera de la ciudad simplemente no se cuenta)."""
    idx = {h: i for i, h in enumerate(hexes)}
    W1 = np.zeros((len(hexes), len(hexes)), dtype="float32")
    W2 = np.zeros((len(hexes), len(hexes)), dtype="float32")
    for h, i in idx.items():
        for k, W in ((1, W1), (2, W2)):
            for v in h3.grid_ring(h, k):
                j = idx.get(v)
                if j is not None:
                    W[i, j] = 1.0
    return W1, W2


def actividad(N: np.ndarray, tau: float) -> np.ndarray:
    """A_i(t) = φ·A_i(t-1) + (1-φ)·N_i(t-1), con φ = exp(-1/τ).

    Es la recursión que hace tratable al Hawkes: en vez de sumar sobre todo el
    pasado para cada t (O(T²)), el núcleo exponencial se acumula en O(T). El
    desfasaje de un día es lo que garantiza que λ_i(t) solo use información
    estrictamente anterior a t — sin eso el modelo se predice a sí mismo.
    """
    phi = float(np.exp(-1.0 / tau))
    A = np.zeros_like(N)
    for t in range(1, N.shape[1]):
        A[:, t] = phi * A[:, t - 1] + (1.0 - phi) * N[:, t - 1]
    return A


# ------------------------------------------------------------------ ajuste

def armar_diseno(As: list[np.ndarray], W1: np.ndarray, W2: np.ndarray) -> np.ndarray:
    """Por cada escala temporal, tres covariables: propia, anillo 1, anillo 2."""
    capas = []
    for A in As:
        capas += [A, W1 @ A, W2 @ A]
    return np.stack(capas)


def ramificacion(theta: np.ndarray) -> float:
    """Hijos esperados por delito: propio + 6 vecinos de anillo 1 + 12 de anillo 2."""
    return float(theta[0] + 6 * theta[1] + 12 * theta[2])


def nll_y_grad(params: np.ndarray, X: np.ndarray, y: np.ndarray,
               hex_idx: np.ndarray, n_hex: int) -> tuple[float, np.ndarray]:
    """Log-verosimilitud de Poisson negativa y su gradiente.

    λ = μ[hex] + θ·X, con enlace identidad (no log): es lo que corresponde para
    un Hawkes, donde el fondo y la excitación se SUMAN. Con enlace log se
    multiplicarían y θ dejaría de leerse como cantidad de hijos.
    """
    mu, theta = params[:n_hex], params[n_hex:]
    lam = mu[hex_idx] + theta @ X
    np.maximum(lam, EPS, out=lam)

    nll = float(lam.sum() - (y * np.log(lam)).sum())
    r = 1.0 - y / lam                      # d(nll)/d(lambda)
    g_theta = X @ r
    g_mu = np.bincount(hex_idx, weights=r, minlength=n_hex)
    return nll, np.concatenate([g_mu, g_theta])


def ajustar(As_tr: list[np.ndarray], N_tr: np.ndarray, W1, W2) -> tuple[np.ndarray, np.ndarray]:
    n_hex, T = N_tr.shape
    X = armar_diseno(As_tr, W1, W2).reshape(3 * len(As_tr), -1)
    y = N_tr.reshape(-1)
    hex_idx = np.repeat(np.arange(n_hex), T)

    p0 = np.concatenate([N_tr.mean(axis=1),
                         np.tile([0.05, 0.005, 0.001], len(As_tr))])
    lim = [(1e-8, None)] * n_hex + [(0.0, None)] * (3 * len(As_tr))
    res = minimize(nll_y_grad, p0, args=(X, y, hex_idx, n_hex), jac=True,
                   method="L-BFGS-B", bounds=lim,
                   options={"maxiter": 800, "maxfun": 1000})
    return res.x[:n_hex], res.x[n_hex:]


def predecir(mu: np.ndarray, theta: np.ndarray, As: list[np.ndarray], W1, W2) -> np.ndarray:
    X = armar_diseno(As, W1, W2)
    return mu[:, None] + np.tensordot(theta, X, axes=(0, 0))


def nll_de(pred: np.ndarray, N: np.ndarray) -> float:
    lam = np.maximum(pred, EPS)
    return float(lam.sum() - (N * np.log(lam)).sum()) / N.size


# ------------------------------------------------------------------ métricas

def recall_en(pred: np.ndarray, real: np.ndarray, k: float) -> float:
    """% de delitos reales del test que caen en el top-K% de hexágonos según el
    riesgo total predicho — misma definición que train_baseline.recall_at_k."""
    p, r = pred.sum(axis=1), real.sum(axis=1)
    top = max(1, int(round(len(p) * k)))
    return float(r[np.argsort(-p)][:top].sum() / r.sum())


def pai_pei(pred: np.ndarray, real: np.ndarray, k: float) -> tuple[float, float]:
    p, r = pred.sum(axis=1), real.sum(axis=1)
    top = max(1, int(round(len(p) * k)))
    cap = r[np.argsort(-p)][:top].sum()
    techo = np.sort(r)[::-1][:top].sum()
    pai = (cap / r.sum()) / k
    return float(pai), float(pai / ((techo / r.sum()) / k))


def evaluar(nombre: str, pred: np.ndarray, real: np.ndarray) -> dict:
    fila = {
        "modelo": nombre,
        "mae": float(np.abs(real - pred).mean()),
        "rmse": float(np.sqrt(((real - pred) ** 2).mean())),
        "sesgo_nivel": float(pred.sum() / real.sum()),
    }
    for k in KS:
        fila[f"recall_{int(k * 100)}"] = recall_en(pred, real, k)
    for k in (0.10, 0.20):
        pai, pei = pai_pei(pred, real, k)
        fila[f"pai_{int(k * 100)}"], fila[f"pei_{int(k * 100)}"] = pai, pei
    return fila


# ------------------------------------------------------------------ LightGBM

def pred_lightgbm_por_dia(fechas: pd.DatetimeIndex, hexes: list[str],
                          mascara_test: np.ndarray) -> np.ndarray | None:
    """El LightGBM de producción, agregado de hex×día×turno a hex×día, para que
    las tres filas de la tabla se midan sobre exactamente las mismas celdas."""
    try:
        import lightgbm as lgb
        from train_baseline import FEATURES_COLS
        from train_incertidumbre import leer_columna_achicada
    except ImportError as e:
        print(f"  (se omite LightGBM: {e})")
        return None

    ruta = FEATURES / "modelos" / "modelo_nucleo_v1.txt"
    if not ruta.exists():
        print("  (se omite LightGBM: falta modelo_nucleo_v1.txt)")
        return None

    import pyarrow.parquet as pq
    f = pq.read_table(FEATURES / "training_table.parquet",
                      columns=["fecha"]).column("fecha").to_pandas()
    es_test = (f.dt.year == 2025).to_numpy()
    fechas_test = f[es_test].dt.normalize().to_numpy()
    del f
    gc.collect()

    cols = {}
    for c in FEATURES_COLS:   # hex_id ya está adentro, es una de las categóricas
        s = leer_columna_achicada(c)
        cols[c] = s[es_test].reset_index(drop=True)
        del s
        gc.collect()
    X = pd.DataFrame({c: cols[c] for c in FEATURES_COLS})

    pred = np.clip(lgb.Booster(model_file=str(ruta)).predict(X), 0, None)
    hex_test = cols["hex_id"].astype(str).to_numpy()
    del X, cols
    gc.collect()

    idx_hex = {h: i for i, h in enumerate(hexes)}
    idx_fecha = {f: i for i, f in enumerate(fechas[mascara_test])}
    M = np.zeros((len(hexes), int(mascara_test.sum())), dtype="float64")
    hi = np.array([idx_hex.get(h, -1) for h in hex_test])
    fi = np.array([idx_fecha.get(pd.Timestamp(x), -1) for x in fechas_test])
    ok = (hi >= 0) & (fi >= 0)
    np.add.at(M, (hi[ok], fi[ok]), pred[ok])
    return M


# ------------------------------------------------------------------ main

def main() -> None:
    N, hexes, fechas = cargar_matriz()
    W1, W2 = matrices_anillo(hexes)
    print(f"Grilla: {N.shape[0]} hexágonos × {N.shape[1]:,} días | "
          f"{int(N.sum()):,} delitos | vecinos anillo 1: {W1.sum(axis=1).mean():.1f} "
          f"| anillo 2: {W2.sum(axis=1).mean():.1f}")

    anio = fechas.year.to_numpy()
    tr, va, te = anio <= 2023, anio == 2024, anio == 2025
    print(f"train {tr.sum():,} días | val {va.sum():,} | test {te.sum():,}\n")

    # --- etapa 1: una sola escala temporal, barrida de medio día a un año ---
    print("Etapa 1 — una escala. Ajuste en train, elección por verosimilitud en val:")
    corridas = []
    for tau in TAUS:
        A = actividad(N, tau)
        mu, th = ajustar([A[:, tr]], N[:, tr], W1, W2)
        nll_va = nll_de(predecir(mu, th, [A[:, va]], W1, W2), N[:, va])
        corridas.append({"tau": tau, "nll_val": nll_va, "mu": mu, "theta": th,
                         "n": ramificacion(th)})
        print(f"  tau={tau:>5}d  NLL(val)={nll_va:.5f}  "
              f"th=[{th[0]:.4f} {th[1]:.5f} {th[2]:.5f}]  ramificacion n={ramificacion(th):.3f}")
        del A
        gc.collect()

    mejor = min(corridas, key=lambda c: c["nll_val"])
    mu, th, tau = mejor["mu"], mejor["theta"], mejor["tau"]
    print(f"\n  Mejor: tau={tau} días, n={mejor['n']:.3f}.")
    if tau >= TAUS[-2]:
        print("  ATENCIÓN: la verosimilitud sigue mejorando con memorias de meses. "
              "Un near-repeat\n  real decae en días — esto parece un estimador "
              "adaptativo del nivel local, no contagio.")

    # --- etapa 2: dos escalas, para separar contagio de deriva lenta ---
    # Si el término rápido conserva peso cuando uno lento ya absorbe la deriva
    # del nivel, hay near-repeat de verdad. Si se apaga, lo que la etapa 1 leía
    # como "contagio" era nada más que el nivel local moviéndose despacio.
    print(f"\nEtapa 2 — dos escalas: una rápida contra una lenta fija de {TAU_LENTO} días.")
    A_lento = actividad(N, TAU_LENTO)
    dobles = []
    for tf in TAUS_RAPIDOS:
        A_rap = actividad(N, tf)
        mu2, th2 = ajustar([A_rap[:, tr], A_lento[:, tr]], N[:, tr], W1, W2)
        nll_va = nll_de(predecir(mu2, th2, [A_rap[:, va], A_lento[:, va]], W1, W2), N[:, va])
        n_rap, n_len = ramificacion(th2[:3]), ramificacion(th2[3:])
        dobles.append({"tau_rapido": tf, "nll_val": nll_va, "mu": mu2, "theta": th2,
                       "n_rapido": n_rap, "n_lento": n_len,
                       "A_rap": A_rap if tf == TAUS_RAPIDOS[0] else None})
        print(f"  tau_rapido={tf:>2}d  NLL(val)={nll_va:.5f}  "
              f"n_rapido={n_rap:.4f}  n_lento={n_len:.3f}  "
              f"-> el rápido explica el {n_rap / (n_rap + n_len):.1%} de la excitación")
        if tf != TAUS_RAPIDOS[0]:
            del A_rap
            gc.collect()

    mejor2 = min(dobles, key=lambda c: c["nll_val"])
    print(f"\n  Mejor combinación: rápido de {mejor2['tau_rapido']} días. "
          f"n_rápido={mejor2['n_rapido']:.4f} contra n_lento={mejor2['n_lento']:.3f}.")

    # --- evaluación en test ---
    A = actividad(N, tau)
    real = N[:, te]
    filas = [evaluar("hawkes_1escala", predecir(mu, th, [A[:, te]], W1, W2), real)]

    A_rap = actividad(N, mejor2["tau_rapido"])
    filas.append(evaluar("hawkes_2escalas",
                         predecir(mejor2["mu"], mejor2["theta"],
                                  [A_rap[:, te], A_lento[:, te]], W1, W2), real))

    # El mismo modelo sin el término rápido, REAJUSTADO — no alcanza con poner
    # theta_rapido=0 sobre el ajuste anterior: eso deja el fondo compensando una
    # excitación que ya no está y el modelo subpredice el nivel un 30%, lo que
    # baja el MAE artificialmente sobre datos tan ralos. Se reajusta μ.
    mu_lento, th_lento = ajustar([A_lento[:, tr]], N[:, tr], W1, W2)
    filas.append(evaluar("hawkes_solo_lento",
                         predecir(mu_lento, th_lento, [A_lento[:, te]], W1, W2), real))

    media_hist = N[:, tr].mean(axis=1)
    filas.append(evaluar("promedio_historico",
                         np.repeat(media_hist[:, None], te.sum(), axis=1), real))

    print("\nAgregando el LightGBM de producción al mismo grano...")
    lgbm = pred_lightgbm_por_dia(fechas, hexes, te)
    if lgbm is not None:
        filas.append(evaluar("lightgbm", lgbm, real))

    res = pd.DataFrame(filas)
    base = res.loc[res.modelo == "promedio_historico", "mae"].iloc[0]
    res["mejora_vs_historico"] = (base - res["mae"]) / base
    res.insert(1, "tau_1escala", tau)
    res.insert(2, "n_1escala", mejor["n"])
    res.insert(3, "tau_rapido", mejor2["tau_rapido"])
    res.insert(4, "n_rapido", mejor2["n_rapido"])
    res.insert(5, "n_lento", mejor2["n_lento"])

    cols = ["modelo", "mae", "rmse", "sesgo_nivel", "recall_10", "recall_20",
            "recall_30", "pai_10", "pei_10", "mejora_vs_historico"]
    print("\n" + "=" * 108)
    print(res[cols].to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print("=" * 108)
    print("Leer el MAE con cuidado: a grano hexágono×día el 82% de las celdas es cero, así")
    print("que subpredecir baja el MAE. La columna sesgo_nivel dice si un modelo está")
    print("ganando por calibrar bien o por tirar bajo; RMSE y Recall@K no tienen ese sesgo.")

    res.to_parquet(SALIDA, index=False)
    print(f"\nGuardado: {SALIDA.name}")


if __name__ == "__main__":
    main()
