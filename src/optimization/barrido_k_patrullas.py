"""
Curva de cobertura vs. K para el Módulo A — cuánto riesgo cubre cada
presupuesto de patrullas, no solo el K que esté fijado en
`modulo_a_patrullas.py`.

Por qué un script aparte y no un loop dentro de modulo_a_patrullas.main():
lo caro de ese script no es resolver el MCLP, es armar la matriz de
cobertura por distancia de red (un Dijkstra con corte desde cada uno de los
476 candidatos sobre el grafo vial, ~6s). Resolver el MCLP para un K dado,
una vez que la matriz existe, tarda menos de un segundo. Correr el script
entero una vez por valor de K recalcularía la matriz cada vez — acá se
calcula una sola vez y se reusa para los 11 valores, así el barrido completo
sale en ~10s en vez de ~1 minuto.

Reusa las funciones de modulo_a_patrullas.py sin duplicar la formulación:
si cambia el MCLP, la restricción de equidad o el radio de cobertura, este
barrido hereda el cambio.

Salida: `data/features/modulo_a_curva_k.json` — la usa el material de
presentación del Módulo A (tabla de escenarios y curva de cobertura).
"""

from __future__ import annotations

import json
from pathlib import Path

import osmnx as ox

from modulo_a_patrullas import (
    GRAFO_PATH, RADIO_COBERTURA_M, TURNO,
    cargar_candidatos, cargar_demanda, cobertura_lograda,
    matriz_cobertura_red, resolver_mclp,
)

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
SALIDA = FEATURES / "modulo_a_curva_k.json"

# Arranca en 5 a propósito: es infactible y el resultado lo documenta. La
# restricción de equidad (>=1 hexágono cubierto por cada una de las 15
# comunas) no se puede satisfacer con tan pocas unidades, y que el modelo
# devuelva "no hay plan" en vez de uno que abandone comunas es parte de lo
# que hay que mostrar, no un caso a esconder.
KS = [5, 10, 15, 20, 30, 40, 50, 60, 75, 90, 110]


def main() -> None:
    demanda = cargar_demanda()
    candidatos = cargar_candidatos(demanda)
    n_comunas = demanda["comuna_id"].nunique()
    print(f"Demanda: {len(demanda)} hexágonos (turno {TURNO}, {n_comunas} comunas) | "
          f"Candidatos: {len(candidatos)} | R={RADIO_COBERTURA_M}m de calle real")

    print("Cargando grafo vial y calculando la matriz de cobertura (una sola vez)...")
    G = ox.io.load_graphml(GRAFO_PATH)
    cobertura = matriz_cobertura_red(demanda, candidatos, G)
    print(f"Grafo: {G.number_of_nodes():,} nodos, {G.number_of_edges():,} tramos")

    idx_actual = candidatos.index[candidatos["tipo"] == "comisaría existente"].tolist()
    pct_actual = cobertura_lograda(demanda, cobertura, idx_actual)
    print(f"\nCobertura ACTUAL ({len(idx_actual)} comisarías reales): {pct_actual:.1%}\n")

    resultado = {
        "turno": TURNO,
        "radio_m": RADIO_COBERTURA_M,
        "n_demanda": int(len(demanda)),
        "n_candidatos": int(len(candidatos)),
        "n_comisarias": len(idx_actual),
        "n_comunas": int(n_comunas),
        "cobertura_actual": float(pct_actual),
        "curva": [],
    }

    for k in KS:
        elegidos, estado = resolver_mclp(demanda, candidatos, cobertura, k, devolver_estado=True)
        if estado != "Optimal":
            # con estado != Optimal las variables del solver no representan una
            # solución válida — se registra el K como infactible y se descarta
            # la cobertura, en vez de reportar un número sin sentido.
            print(f"K={k:3d} -> {estado} (la restricción de equidad no se puede satisfacer)")
            resultado["curva"].append({"k": k, "estado": estado, "cobertura": None})
            continue

        pct = cobertura_lograda(demanda, cobertura, elegidos)
        tipos = candidatos.iloc[elegidos]["tipo"].value_counts()
        n_com = int(tipos.get("comisaría existente", 0))
        resultado["curva"].append({
            "k": k, "estado": estado, "cobertura": float(pct),
            "reusa_comisaria": n_com, "puestos_nuevos": int(len(elegidos) - n_com),
        })
        supera = " <- supera a las comisarías actuales" if pct > pct_actual else ""
        print(f"K={k:3d} -> {pct:.1%} ({n_com} comisarías + {len(elegidos) - n_com} puestos nuevos){supera}")

    SALIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nGuardado: {SALIDA}")


if __name__ == "__main__":
    main()
