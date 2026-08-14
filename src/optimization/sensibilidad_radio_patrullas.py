"""
El titular del proyecto depende de un supuesto que nunca se probó: los 800m.

El Módulo A dice que las 75 comisarías cubren el 35,1% del riesgo y que las
mismas 75 unidades reubicadas cubrirían el 58,7%. Todo ese cálculo asume que una
patrulla "cubre" 800 metros de calle. Ese número salió del documento de
arquitectura (sección 4.1), no de estos datos.

Ya hay un precedente en el proyecto. En el Módulo C los 30m de buffer también
eran una elección razonable por primeros principios, y al barrerla de 10 a 75m
**el primer puesto se dio vuelta**. El par de los dos primeros aguantaba; el
orden entre ellos no. Nadie hizo la prueba equivalente acá.

Se barre el radio de 300 a 1500m y se mira qué aguanta:

  - la cobertura actual de las 75 comisarías reales
  - la cobertura óptima con K=30, 40 y 75
  - la GANANCIA, en puntos y en relativo — es el titular real
  - el punto de cruce: con cuántas patrullas se iguala a las 75 comisarías
  - cuánto se parece el plan de K=75 al plan de 800m (mismas ubicaciones)

Qué esperar en los extremos, para no confundir un artefacto con un hallazgo: con
radio chico casi ningún hexágono queda cubierto y la restricción de equidad
vuelve el problema infactible; con radio grande todo cubre todo, las dos
coberturas tienden a 100% y la ganancia se aplana sola. La pregunta es si 800
cae en una zona estable o al borde de un precipicio.

Reusa las funciones de modulo_a_patrullas.py, así que si cambia el MCLP o la
restricción de equidad este barrido hereda el cambio. Lo caro es la matriz de
cobertura (un Dijkstra con corte desde cada uno de los 476 candidatos), y hay
que recalcularla una vez por radio porque justamente el radio es el corte.

Salida: data/features/sensibilidad_radio_patrullas.json
"""

from __future__ import annotations

import json
from pathlib import Path

import osmnx as ox

import modulo_a_patrullas as mod_a
from modulo_a_patrullas import (
    GRAFO_PATH, TURNO, cargar_candidatos, cargar_demanda,
    cobertura_lograda, matriz_cobertura_red, resolver_mclp,
)

FEATURES = Path(__file__).resolve().parent.parent.parent / "data" / "features"
SALIDA = FEATURES / "sensibilidad_radio_patrullas.json"

RADIOS = [300, 500, 650, 800, 1000, 1200, 1500]
RADIO_REFERENCIA = 800
KS = [10, 15, 20, 25, 30, 35, 40, 50, 60, 75]
K_TITULAR = 75


def main() -> None:
    demanda = cargar_demanda()
    candidatos = cargar_candidatos(demanda)
    idx_actual = candidatos.index[candidatos["tipo"] == "comisaría existente"].tolist()
    print(f"Demanda: {len(demanda)} hexágonos (turno {TURNO}) | "
          f"Candidatos: {len(candidatos)} | Comisarías reales: {len(idx_actual)}")

    print("Cargando grafo vial...")
    G = ox.io.load_graphml(GRAFO_PATH)

    resultado = {"turno": TURNO, "k_titular": K_TITULAR, "radios": []}
    planes: dict[int, set] = {}

    for radio in RADIOS:
        # matriz_cobertura_red lee el radio como constante del módulo
        mod_a.RADIO_COBERTURA_M = radio
        print(f"\n=== Radio {radio} m ===")
        cobertura = matriz_cobertura_red(demanda, candidatos, G)
        densidad = cobertura.mean()

        pct_actual = cobertura_lograda(demanda, cobertura, idx_actual)
        print(f"  Cobertura actual (75 comisarías): {pct_actual:.1%} | "
              f"densidad de la matriz {densidad:.1%}")

        fila = {"radio_m": radio, "densidad_matriz": float(densidad),
                "cobertura_actual": float(pct_actual), "por_k": [], "cruce_k": None}

        for k in KS:
            elegidos, estado = resolver_mclp(demanda, candidatos, cobertura, k,
                                             devolver_estado=True)
            if estado != "Optimal":
                print(f"    K={k:>3}: {estado} (equidad infactible)")
                fila["por_k"].append({"k": k, "estado": estado, "cobertura": None})
                continue
            pct = cobertura_lograda(demanda, cobertura, elegidos)
            n_com = int((candidatos.iloc[elegidos]["tipo"] == "comisaría existente").sum())
            fila["por_k"].append({"k": k, "estado": estado, "cobertura": float(pct),
                                  "reusa_comisaria": n_com})
            if fila["cruce_k"] is None and pct >= pct_actual:
                fila["cruce_k"] = k
            if k == K_TITULAR:
                planes[radio] = set(elegidos)
                fila["cobertura_k_titular"] = float(pct)
                fila["reusa_comisaria_k_titular"] = n_com
                fila["ganancia_pp"] = float(pct - pct_actual)
                fila["ganancia_relativa"] = float(pct / pct_actual - 1)
            print(f"    K={k:>3}: {pct:>6.1%}  ({n_com} comisarías reusadas)"
                  + ("  <- iguala a las 75 actuales" if fila["cruce_k"] == k else ""))

        resultado["radios"].append(fila)

    # ¿el plan es el mismo, o solo el número se parece?
    base = planes.get(RADIO_REFERENCIA, set())
    for fila in resultado["radios"]:
        p = planes.get(fila["radio_m"], set())
        fila["solape_plan_vs_800"] = len(p & base) / len(base) if base else None

    print("\n" + "=" * 96)
    print(f"{'radio':>6} {'actual':>8} {'K=75':>8} {'ganancia':>9} {'relativa':>9} "
          f"{'cruce':>6} {'plan igual a 800m':>18}")
    print("-" * 96)
    for f in resultado["radios"]:
        if "cobertura_k_titular" not in f:
            print(f"{f['radio_m']:>6} {f['cobertura_actual']:>7.1%}  (sin solución óptima en K=75)")
            continue
        print(f"{f['radio_m']:>6} {f['cobertura_actual']:>7.1%} {f['cobertura_k_titular']:>7.1%} "
              f"{f['ganancia_pp']:>8.1%} {f['ganancia_relativa']:>8.1%} "
              f"{str(f['cruce_k']):>6} {f['solape_plan_vs_800']:>17.1%}")
    print("=" * 96)

    con_k = [f for f in resultado["radios"] if "ganancia_relativa" in f]
    rel = [f["ganancia_relativa"] for f in con_k]
    pp = [f["ganancia_pp"] for f in con_k]
    cruces = [f["cruce_k"] for f in resultado["radios"] if f["cruce_k"] is not None]
    solapes = [f["solape_plan_vs_800"] for f in con_k if f["radio_m"] != RADIO_REFERENCIA]

    # Las dos formas de contar la ganancia NO se comportan igual, y conviene no
    # mezclarlas: la relativa lleva la cobertura actual en el denominador, y esa
    # se derrumba con radio chico (5,4% a 300m), así que el cociente explota sin
    # que pase nada interesante. La diferencia en puntos no tiene ese problema.
    print(f"\nGanancia en PUNTOS:   {min(pp):.1%} a {max(pp):.1%}  -> "
          f"{'ROBUSTA' if max(pp) - min(pp) < 0.25 else 'sensible'}")
    print(f"Ganancia RELATIVA:    {min(rel):.0%} a {max(rel):.0%}  -> depende del radio, "
          f"pero es un artefacto del denominador")
    print(f"Punto de cruce:       K={min(cruces)} a K={max(cruces)} "
          f"(nunca peor que {max(cruces)})")
    print(f"Plan contra el de 800m: {min(solapes):.0%} a {max(solapes):.0%} de ubicaciones "
          f"en común -> {'ROBUSTO' if min(solapes) > 0.6 else 'EL PLAN SÍ SE MUEVE'}")
    print("\nOjo con los radios grandes: a 1200m la cobertura óptima ya es 97,7% y a 1500m")
    print("llega a 100%, así que el problema se vuelve degenerado —hay muchos conjuntos de")
    print("75 ubicaciones que empatan— y el solape bajo ahí dice poco. El caso informativo")
    print("es 1000m, que todavía no satura (83,1%) y aun así comparte solo el 28%.")

    mod_a.RADIO_COBERTURA_M = RADIO_REFERENCIA   # restaurar el default del módulo
    SALIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nGuardado: {SALIDA.name}")


if __name__ == "__main__":
    main()
