"""
Motor de escenarios — P1 de la auditoría técnica externa (sección 8), la
brecha más grande contra la visión del producto: el brief pedía poder
responder "¿qué recursos deberían moverse?", "¿cuál sería el impacto de
moverlos?" y "¿qué ocurriría si cambian las condiciones?" de forma
interactiva, y hasta ahora eso requería editar constantes a mano en un
script y volver a correrlo.

No es un gemelo digital con simulación basada en agentes (el techo
teórico, fuera de alcance de una sola persona en esta máquina) — es la
ruta pragmática que señaló la auditoría: reutilizar el pipeline ya
construido (Capa 1 + Módulo A) detrás de una función de escenarios, en
vez de investigación nueva.

Dos tipos de escenario, porque responden preguntas distintas del brief:

1. **Escenario de recursos** ("¿qué pasa si tengo más/menos patrullas?"):
   mismo riesgo predicho, cambia K_PATRULLAS o el radio de cobertura, se
   re-resuelve el MCLP de Módulo A y se compara la cobertura lograda.

2. **Escenario de condiciones** ("¿qué pasa si mejoro el alumbrado acá?"):
   se perturban features estáticas de hexágonos puntuales (alumbrado,
   cámaras, espacio verde...), se re-predice el riesgo con el modelo
   entrenado, y se compara contra el riesgo base — sin re-entrenar nada.

El "estado base" (hoy) toma, para cada hex×turno, la fila más reciente
de training_table.parquet (2025-12-31) — sus lags/rolling ya reflejan el
historial real hasta esa fecha; lo único que un escenario cambia son las
features estáticas (infraestructura) o los parámetros de Módulo A, nunca
el historial delictivo en sí (eso no es algo que se pueda simular sin
inventar delitos que no pasaron).
"""

from __future__ import annotations

import sys
from pathlib import Path

import lightgbm as lgb
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "model_core"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "optimization"))
from train_baseline import CATEGORICAS, FEATURES_COLS  # noqa: E402
import modulo_a_patrullas as mod_a  # noqa: E402

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
MODELS_DIR = FEATURES / "modelos"

FEATURES_ESTATICAS_MODIFICABLES = [
    "n_luminarias", "n_camaras", "pct_espacio_verde", "poblacion_hex",
    "n_escuelas_cerca", "n_hospitales_cerca", "n_universidades_cerca", "n_cajeros_cerca",
]


def cargar_estado_base() -> pd.DataFrame:
    """Última fecha disponible de training_table.parquet, una fila por
    hex×turno — el "hoy" simulado sobre el que corren los escenarios."""
    tabla = pd.read_parquet(FEATURES / "training_table.parquet")
    ultima_fecha = tabla["fecha"].max()
    estado = tabla[tabla["fecha"] == ultima_fecha].copy().reset_index(drop=True)
    for col in CATEGORICAS:
        estado[col] = estado[col].astype("category")
    print(f"Estado base: {ultima_fecha.date()}, {len(estado)} filas (hex×turno)")
    return estado


def cargar_modelo() -> lgb.Booster:
    return lgb.Booster(model_file=str(MODELS_DIR / "modelo_nucleo_v1.txt"))


def predecir(estado: pd.DataFrame, modelo: lgb.Booster) -> pd.Series:
    return pd.Series(np.clip(modelo.predict(estado[FEATURES_COLS]), 0, None), index=estado.index)


def escenario_condiciones(nombre: str, modificaciones: dict[str, dict[str, float]], turno: str = "Tarde") -> pd.DataFrame:
    """modificaciones: {hex_id: {feature: nuevo_valor}} — ej.
    {"88c2e31133fffff": {"n_luminarias": 40}} simula agregar luminarias
    ahí. Devuelve la comparación riesgo base vs. escenario por hex
    modificado."""
    estado = cargar_estado_base()
    estado_turno = estado[estado["turno"] == turno].copy()
    modelo = cargar_modelo()

    riesgo_base = predecir(estado_turno, modelo)

    estado_escenario = estado_turno.copy()
    for hex_id, cambios in modificaciones.items():
        idx = estado_escenario.index[estado_escenario["hex_id"] == hex_id]
        for feature, valor in cambios.items():
            if feature not in FEATURES_ESTATICAS_MODIFICABLES:
                raise ValueError(f"'{feature}' no es una feature estática modificable — ver FEATURES_ESTATICAS_MODIFICABLES")
            estado_escenario.loc[idx, feature] = valor
    riesgo_escenario = predecir(estado_escenario, modelo)

    comparacion = estado_turno[["hex_id"]].copy()
    comparacion["riesgo_base"] = riesgo_base.to_numpy()
    comparacion["riesgo_escenario"] = riesgo_escenario.to_numpy()
    comparacion["delta"] = comparacion["riesgo_escenario"] - comparacion["riesgo_base"]
    comparacion["delta_pct"] = comparacion["delta"] / comparacion["riesgo_base"].replace(0, np.nan)

    modificados = comparacion[comparacion["hex_id"].isin(modificaciones.keys())]
    print(f"\n=== Escenario de condiciones: {nombre} (turno {turno}) ===")
    print(f"Riesgo total ciudad: {comparacion['riesgo_base'].sum():.2f} -> {comparacion['riesgo_escenario'].sum():.2f} "
          f"({(comparacion['riesgo_escenario'].sum() / comparacion['riesgo_base'].sum() - 1):+.2%})")
    print(f"Hexágonos modificados ({len(modificados)}):")
    print(modificados.to_string(index=False))
    return comparacion


def escenario_recursos(nombre: str, k_patrullas: int, turno: str = "Tarde", radio_cobertura_m: int | None = None) -> dict:
    """Cambia K (y opcionalmente el radio) y re-resuelve Módulo A sobre el
    mismo riesgo_predicho.parquet — compara contra la cobertura actual
    (75 comisarías) y contra el K de referencia del proyecto (40)."""
    radio = radio_cobertura_m or mod_a.RADIO_COBERTURA_M

    demanda = pd.read_parquet(FEATURES / "riesgo_predicho.parquet")
    demanda = demanda[demanda["turno"] == turno].copy().reset_index(drop=True)
    candidatos = mod_a.cargar_candidatos(demanda)

    G = ox.io.load_graphml(mod_a.GRAFO_PATH)
    mod_a.RADIO_COBERTURA_M = radio  # el radio se lee como constante de módulo en matriz_cobertura_red
    cobertura = mod_a.matriz_cobertura_red(demanda, candidatos, G)

    idx_actual = candidatos.index[candidatos["tipo"] == "comisaría existente"].tolist()
    pct_actual = mod_a.cobertura_lograda(demanda, cobertura, idx_actual)

    elegidos = mod_a.resolver_mclp(demanda, candidatos, cobertura, k_patrullas)
    pct_escenario = mod_a.cobertura_lograda(demanda, cobertura, elegidos)
    mod_a.RADIO_COBERTURA_M = 800  # restaurar default del módulo

    resultado = {
        "nombre": nombre, "k_patrullas": k_patrullas, "radio_cobertura_m": radio,
        "cobertura_actual_75_comisarias": pct_actual, "cobertura_escenario": pct_escenario,
        "ganancia_vs_actual": pct_escenario - pct_actual,
    }
    print(f"\n=== Escenario de recursos: {nombre} ===")
    print(f"K={k_patrullas} patrullas, radio={radio}m -> cobertura {pct_escenario:.1%} "
          f"(actual con 75 comisarías: {pct_actual:.1%}, ganancia {resultado['ganancia_vs_actual']:+.1%})")
    return resultado


if __name__ == "__main__":
    # Escenario de condiciones: mejorar alumbrado en los 5 hexágonos de
    # mayor riesgo predicho, a ver cuánto cae el riesgo del modelo.
    riesgo_actual = pd.read_parquet(FEATURES / "riesgo_predicho.parquet")
    riesgo_actual = riesgo_actual[riesgo_actual["turno"] == "Tarde"].sort_values("score_riesgo", ascending=False)
    top5_riesgosos = riesgo_actual["hex_id"].head(5).tolist()

    estado_actual = cargar_estado_base()
    n_luminarias_actual = estado_actual.set_index("hex_id")["n_luminarias"].to_dict()
    mods = {h: {"n_luminarias": n_luminarias_actual.get(h, 0) * 3 + 20} for h in top5_riesgosos}
    escenario_condiciones("Triplicar alumbrado en el top 5 de mayor riesgo", mods)

    # Escenarios de recursos: menos y más patrullas que el K=40 de referencia.
    escenario_recursos("Presupuesto reducido", k_patrullas=20)
    escenario_recursos("Presupuesto de referencia", k_patrullas=40)
    escenario_recursos("Presupuesto ampliado", k_patrullas=60)
