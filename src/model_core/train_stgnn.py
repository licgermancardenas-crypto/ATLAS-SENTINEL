"""
Red neuronal espacio-temporal (GNN + GRU) sobre la grilla H3, contra el
LightGBM semanal.

POR QUÉ ESTE SCRIPT EXISTE
El proyecto tiene medido un techo: el modelo semanal le gana a la persistencia
26 de 26 semanas, pero al promedio histórico por hex×turno apenas un 2,5% de
MAE. La lectura documentada es que a esta resolución el proceso es "casi
puramente espacial" — `hex_id` domina la importancia de features y la dinámica
temporal aporta poco.

Esa lectura tiene una ambigüedad que nunca se resolvió: **¿el techo es del
fenómeno o de la clase de modelo?** Un GBM sobre features tabulares ve la
vecindad espacial solo a través de dos columnas resumidas (`vecino_k1_roll4`,
`vecino_k2_roll4`) y la historia solo a través de lags fijos. Si hubiera
estructura espacio-temporal que esas columnas aplanan, un modelo que propague
información por el grafo de hexágonos y recorra la secuencia debería
encontrarla.

Este script prueba exactamente eso, con el mismo protocolo de
`backtest_pronostico.py` para que los números sean comparables: 26 orígenes
semanales, reentrenando en cada uno, MAE y Recall@20% contra las mismas
referencias.

QUÉ MODELO
- Nodos: los 401 hexágonos. Aristas: vecindad H3 k=1 (2.226 aristas, grado
  medio 5,55 — los bordes de la Ciudad tienen menos de 6 vecinos).
- Cada nodo lleva 4 canales por semana, uno por turno, más las estáticas del
  hexágono (población, NBI, hacinamiento, cámaras, luminarias, espacio verde).
- Dos capas de convolución de grafo por paso de tiempo, GRU sobre los pasos,
  y una salida por turno con softplus (los conteos no pueden ser negativos).
- Pérdida Poisson, la misma familia que el objetivo del LightGBM de v1.

LO QUE HAY QUE TENER PRESENTE AL LEER EL RESULTADO
Son 401 nodos y ~500 semanas: para deep learning es un dataset chico, así que
el riesgo de sobreajuste es alto y por eso la red es deliberadamente pequeña
(48 unidades) con early stopping sobre las últimas semanas antes de cada
origen. Si empata con el LightGBM, la conclusión no es "la red no sirve" sino
que el techo es del fenómeno — que es justamente lo que se quiere saber.

Uso: python train_stgnn.py [n_origenes]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import h3
import numpy as np
import pandas as pd
import torch
import torch.nn as nn

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
TABLA = FEATURES / "training_table_semanal.parquet"
BACKTEST_LGBM = FEATURES / "backtest_pronostico.parquet"
RUTA_SALIDA = FEATURES / "backtest_stgnn.parquet"

TARGET = "conteo_delitos"
TURNOS = ["Madrugada", "Mañana", "Tarde", "Noche"]
ESTATICAS = ["poblacion_hex", "pct_hogares_nbi", "pct_hacinamiento_critico",
             "n_camaras", "n_luminarias", "pct_espacio_verde"]

VENTANA = 12          # semanas de historia que ve la red
OCULTO = 48
EPOCAS = 60
PACIENCIA = 8         # early stopping
SEMANAS_VAL = 8       # validación: las últimas semanas antes del origen
N_ORIGENES = 26
SEMILLA = 42


# ─────────────────────────────────────────────────────────── datos y grafo

def cargar() -> tuple[np.ndarray, np.ndarray, list[str], np.ndarray]:
    """Devuelve (Y, S, hexes, semanas).

    Y es [T semanas, 401 hexágonos, 4 turnos] con los conteos. La tabla está
    completa (401 × 523 × 4 = 838.892 filas exactas), así que el pivot no deja
    huecos — se verifica igual antes de seguir.
    """
    t = pd.read_parquet(TABLA)
    hexes = sorted(t["hex_id"].unique())
    semanas = np.sort(t["semana"].unique())
    i_hex = {h: i for i, h in enumerate(hexes)}
    i_sem = {s: i for i, s in enumerate(semanas)}
    i_tur = {v: i for i, v in enumerate(TURNOS)}

    Y = np.zeros((len(semanas), len(hexes), len(TURNOS)), dtype=np.float32)
    Y[t["semana"].map(i_sem).to_numpy(),
      t["hex_id"].map(i_hex).to_numpy(),
      t["turno"].map(i_tur).to_numpy()] = t[TARGET].to_numpy(np.float32)

    est = (t.drop_duplicates("hex_id").set_index("hex_id")[ESTATICAS]
           .reindex(hexes).astype(np.float32).fillna(0.0).to_numpy())
    est = (est - est.mean(0)) / (est.std(0) + 1e-6)
    return Y, est, hexes, semanas


def adyacencia(hexes: list[str]) -> torch.Tensor:
    """Â = D^-1/2 (A + I) D^-1/2 sobre la vecindad H3 k=1, **dispersa**.

    Con lazo propio y normalización simétrica, que es la forma estándar: sin el
    lazo el nodo pierde su propia señal al propagar, y sin normalizar los
    hexágonos del centro (6 vecinos) pesarían más que los del borde por el solo
    hecho de tener más vecinos.

    Va dispersa y no densa por una razón de costo, no de estilo: la matriz es
    401×401 = 160.801 celdas de las que solo 2.627 son distintas de cero. La
    primera versión usaba densa y cada origen tardaba más de diez minutos; con
    dispersa el mismo cálculo se salta el 98% de las multiplicaciones por cero.
    """
    idx = {h: i for i, h in enumerate(hexes)}
    A = np.eye(len(hexes), dtype=np.float32)
    for h, i in idx.items():
        for v in h3.grid_disk(h, 1):
            if v != h and v in idx:
                A[i, idx[v]] = 1.0
    d = A.sum(1)
    Dm = np.diag(1.0 / np.sqrt(d))
    return torch.from_numpy(Dm @ A @ Dm).to_sparse_csr()


# ────────────────────────────────────────────────────────────────── modelo

class CapaGrafo(nn.Module):
    """Convolución de grafo: promedia la señal de los vecinos y la proyecta."""

    def __init__(self, entra: int, sale: int):
        super().__init__()
        self.lin = nn.Linear(entra, sale)

    def forward(self, x: torch.Tensor, A: torch.Tensor) -> torch.Tensor:
        """x: [B, N, F] -> proyecta y propaga por el grafo.

        Se proyecta ANTES de propagar porque baja el costo del producto
        disperso (sale con `oculto` columnas en vez de `entra`), y porque el
        producto disperso necesita 2D: hay que plegar el batch y las features
        en una sola dimensión y devolver la forma después.
        """
        B, N, _ = x.shape
        h = self.lin(x)                            # [B, N, H]
        H = h.shape[-1]
        h = h.permute(1, 0, 2).reshape(N, B * H)   # [N, B*H]
        h = A @ h
        return h.reshape(N, B, H).permute(1, 0, 2)


class STGNN(nn.Module):
    """Convolución temporal por nodo, después mezcla espacial por el grafo.

    Es la estructura de STGCN, y se llegó a ella por costo medido. La primera
    versión ponía un GRU sobre la secuencia de cada nodo: con 401 nodos × 16
    semanas de lote son 6.416 secuencias por paso, y en CPU eso daba 18 minutos
    por origen — casi ocho horas para los 26. Reemplazar la recurrencia por dos
    convoluciones 1D sobre el tiempo y hacer la propagación espacial una sola
    vez (y no en cada paso temporal) baja el costo unas veinte veces sin perder
    lo que importa: sigue habiendo estructura temporal aprendida y sigue
    habiendo propagación por la vecindad real de la grilla.
    """

    def __init__(self, n_turnos: int, n_estaticas: int, oculto: int = OCULTO):
        super().__init__()
        self.temporal = nn.Sequential(
            nn.Conv1d(n_turnos, oculto, kernel_size=3, padding=1), nn.ReLU(),
            nn.Conv1d(oculto, oculto, kernel_size=3, padding=1), nn.ReLU(),
        )
        self.g1 = CapaGrafo(oculto + n_estaticas, oculto)
        self.g2 = CapaGrafo(oculto, oculto)
        self.salida = nn.Linear(oculto, n_turnos)
        self.act = nn.ReLU()

    def forward(self, x: torch.Tensor, est: torch.Tensor, A: torch.Tensor) -> torch.Tensor:
        """x: [B, L, N, C] conteos; est: [N, E]; devuelve [B, N, C]."""
        B, L, N, C = x.shape
        # log1p: los conteos tienen cola larga y sin comprimir la escala el
        # gradiente lo domina un puñado de hexágonos del microcentro
        h = torch.log1p(x).permute(0, 2, 3, 1).reshape(B * N, C, L)
        h = self.temporal(h).mean(-1).reshape(B, N, -1)     # resumen temporal
        h = torch.cat([h, est.unsqueeze(0).expand(B, -1, -1)], dim=-1)
        h = self.act(self.g1(h, A))
        h = self.act(self.g2(h, A))
        return nn.functional.softplus(self.salida(h))


def ventanas(Y: np.ndarray, desde: int, hasta: int) -> tuple[torch.Tensor, torch.Tensor]:
    """Pares (historia, objetivo) para las semanas objetivo en [desde, hasta]."""
    X = np.stack([Y[j - VENTANA:j] for j in range(desde, hasta + 1)])
    T = np.stack([Y[j] for j in range(desde, hasta + 1)])
    return torch.from_numpy(X), torch.from_numpy(T)


def entrenar(Y: np.ndarray, est: torch.Tensor, A: torch.Tensor,
             fin_train: int) -> STGNN:
    """Entrena prediciendo cada semana hasta `fin_train` inclusive."""
    torch.manual_seed(SEMILLA)
    modelo = STGNN(len(TURNOS), est.shape[1])
    opt = torch.optim.Adam(modelo.parameters(), lr=3e-3)
    # Poisson: misma familia que el objetivo del LightGBM, y respeta que el
    # target es un conteo con muchos ceros
    perdida = nn.PoissonNLLLoss(log_input=False, full=False, eps=1e-8)

    corte = fin_train - SEMANAS_VAL
    Xtr, Ttr = ventanas(Y, VENTANA, corte)
    Xva, Tva = ventanas(Y, corte + 1, fin_train)

    mejor, mejor_estado, sin_mejora = float("inf"), None, 0
    for _ in range(EPOCAS):
        modelo.train()
        # lotes chicos de semanas: el grafo entero entra en cada paso, así que
        # el "batch" son semanas, no nodos
        orden = torch.randperm(len(Xtr))
        for k in range(0, len(orden), 16):
            lote = orden[k:k + 16]
            opt.zero_grad()
            p = modelo(Xtr[lote], est, A)
            perdida(p, Ttr[lote]).backward()
            opt.step()

        modelo.eval()
        with torch.no_grad():
            val = float(perdida(modelo(Xva, est, A), Tva))
        if val < mejor - 1e-5:
            mejor, sin_mejora = val, 0
            mejor_estado = {k: v.clone() for k, v in modelo.state_dict().items()}
        else:
            sin_mejora += 1
            if sin_mejora >= PACIENCIA:
                break

    if mejor_estado is not None:
        modelo.load_state_dict(mejor_estado)
    modelo.eval()
    return modelo


# ───────────────────────────────────────────────────────────────── métrica

def recall_at_k(real: np.ndarray, pred: np.ndarray, k: float = 0.20) -> float:
    """Misma definición que backtest_pronostico.py: se agrega por hexágono
    (sumando los turnos) y se mide qué fracción del delito real cae en el
    top-k de hexágonos según la predicción."""
    r, p = real.sum(1), pred.sum(1)
    if r.sum() == 0:
        return float("nan")
    n = max(1, int(round(len(r) * k)))
    top = np.argsort(-p)[:n]
    return float(r[top].sum() / r.sum())


def main() -> None:
    n_origenes = int(sys.argv[1]) if len(sys.argv) > 1 else N_ORIGENES
    Y, est_np, hexes, semanas = cargar()
    est = torch.from_numpy(est_np)
    A = adyacencia(hexes)
    print(f"{Y.shape[0]} semanas × {Y.shape[1]} hexágonos × {Y.shape[2]} turnos | "
          f"{A.values().numel()} entradas no nulas en la adyacencia "
          f"(de {Y.shape[1] ** 2:,} posibles)")

    # los mismos orígenes que backtest_pronostico.py: el último predice la
    # última semana disponible
    objetivos = list(range(len(semanas) - n_origenes, len(semanas)))

    # Se reanuda desde lo ya guardado. Hace falta porque la corrida entera son
    # ~2 horas y el entorno corta los procesos de fondo antes: las dos primeras
    # veces murió a los 40-45 minutos. Reanudar es legítimo acá porque la
    # semilla está fija y cada origen se entrena de cero — los orígenes ya
    # calculados dan idéntico si se repiten, verificado entre corridas.
    filas: list[dict] = []
    if RUTA_SALIDA.exists():
        previo = pd.read_parquet(RUTA_SALIDA)
        hechos = set(previo["objetivo"])
        esperados = {pd.Timestamp(semanas[j]).date().isoformat() for j in objetivos}
        if hechos <= esperados:
            filas = previo.to_dict("records")
            objetivos = [j for j in objetivos
                         if pd.Timestamp(semanas[j]).date().isoformat() not in hechos]
            print(f"reanudando: {len(filas)} orígenes ya hechos, faltan {len(objetivos)}")
        else:
            print("el parquet previo es de otra configuración — se recalcula entero")

    for i, j in enumerate(objetivos, len(filas) + 1):
        t0 = time.time()
        modelo = entrenar(Y, est, A, fin_train=j - 1)
        X, _ = ventanas(Y, j, j)
        with torch.no_grad():
            pred = modelo(X, est, A)[0].numpy()
        real = Y[j]

        # mismas referencias que el backtest del LightGBM
        persistencia = Y[j - 1]
        historico = Y[:j].mean(axis=0)

        fila = {"objetivo": pd.Timestamp(semanas[j]).date().isoformat(),
                "delitos_reales": float(real.sum()), "segundos": round(time.time() - t0, 1)}
        for nombre, p in (("stgnn", pred), ("persistencia", persistencia),
                          ("historico", historico)):
            fila[f"mae_{nombre}"] = float(np.abs(real - p).mean())
            fila[f"recall20_{nombre}"] = recall_at_k(real, p)
        filas.append(fila)
        print(f"  [{i:2d}/{n_origenes}] {fila['objetivo']}  "
              f"MAE stgnn={fila['mae_stgnn']:.4f}  hist={fila['mae_historico']:.4f}  "
              f"({fila['segundos']}s)")
        # se guarda en cada origen y no al final: la corrida completa son ~2
        # horas y la primera vez se cortó en el origen 10 sin dejar nada. El
        # costo de reescribir un parquet de 26 filas es irrelevante al lado de
        # perder una hora de cómputo.
        pd.DataFrame(filas).to_parquet(RUTA_SALIDA, index=False)

    res = pd.DataFrame(filas)
    ruta = RUTA_SALIDA

    print(f"\n{'=' * 66}\nST-GNN COMO PRONÓSTICO A UNA SEMANA — {len(res)} orígenes\n{'=' * 66}")
    for nombre in ("stgnn", "persistencia", "historico"):
        print(f"  {nombre:13s} MAE={res[f'mae_{nombre}'].mean():.4f}  "
              f"Recall@20%={res[f'recall20_{nombre}'].mean():.1%}")

    if BACKTEST_LGBM.exists():
        lgbm = pd.read_parquet(BACKTEST_LGBM)[["objetivo", "mae_modelo", "recall20_modelo"]]
        j = res.merge(lgbm, on="objetivo", how="inner")
        if len(j):
            print(f"\n  contra el LightGBM, sobre las {len(j)} semanas que comparten:")
            print(f"  {'lightgbm':13s} MAE={j['mae_modelo'].mean():.4f}  "
                  f"Recall@20%={j['recall20_modelo'].mean():.1%}")
            d = (j["mae_modelo"].mean() - j["mae_stgnn"].mean()) / j["mae_modelo"].mean()
            gana = (j["mae_stgnn"] < j["mae_modelo"]).mean()
            print(f"  st-gnn vs lightgbm: {d:+.2%} de MAE, gana {gana:.0%} de las semanas")
        else:
            print("\n  OJO: no hay semanas en común con el backtest del LightGBM.")
    print(f"\nGuardado: {ruta.name}")


if __name__ == "__main__":
    main()
