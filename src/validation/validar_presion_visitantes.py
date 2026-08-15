"""Valida el índice de presión de visitantes contra la ENMODO 2018.

El tablero marca la tasa de delito cada 100.000 habitantes en los barrios donde
entra mucha gente que no vive ahí, porque ahí el denominador residencial se
queda corto. El índice que hace esa marca combina molinetes de subte, boletos
de tren y estaciones de EcoBici como percentiles, relativizados por población
(ver `generar_export_dashboard.py`, `_presion_visitantes`).

Ese índice ve tres modos. La pregunta es si alcanza para ordenar la afluencia
real, que incluye también colectivo, auto y a pie.

Historial de lo que fue midiendo este script:

- Con subte + EcoBici: Spearman 0,729. Punto ciego claro en la Comuna 9
  (Liniers, Mataderos), 4ª para la encuesta y 14ª para el índice.
- Sumando el tren (`pipeline/ingest_trenes_boletos.py`): Spearman 0,768, y
  Liniers pasa de percentil 0,12 a 0,83, o sea entra al quinto marcado. La
  Comuna 9 sube a 12ª. Lo que queda sin cubrir es Mataderos, que recibe gente
  en colectivo y del colectivo no hay pasajeros por parada publicados.

La ENMODO 2018 sirve de contraste independiente: es una encuesta domiciliaria
multimodal del AMBA (16.667 hogares, 59.452 viajes) con el destino de cada
viaje georreferenciado a radio censal y código INDEC de comuna. Se compara
contra los viajes que LLEGAN a cada comuna desde otra jurisdicción, por
habitante — que es la definición operativa de "gente que no vive acá".

No se usa para corregir el denominador y la razón está medida: entre 2018 y
2025 el subte perdió 35,3% de pasajeros, pero la caída se concentra justo en
el microcentro (San Nicolás -49,0%, agregado del microcentro -40,2%) contra
-31,1% en el resto, y barrios como Nueva Pompeya apenas -1,0%. Un denominador
de 2018 aplicado a delitos de 2025 sobrecorregiría exactamente los barrios que
la marca quiere señalar. ENMODO sirve para validar el orden, no para fijar el
nivel.

Entrada: data/raw/enmodo/Viajes_ENMODO18.xlsx
  Bajarlo de https://data.buenosaires.gob.ar/dataset/encuesta-movilidad-domiciliaria
  (recurso "Base Viajes", 8,8MB, CC-BY). No se versiona: data/raw/ está en
  .gitignore como el resto de los datos crudos.

Uso: python validar_presion_visitantes.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent.parent
VIAJES = RAIZ / "data" / "raw" / "enmodo" / "Viajes_ENMODO18.xlsx"
COMUNAS = RAIZ / "dashboard" / "public" / "data" / "comunas_resumen.json"

# En la ENMODO las comunas de CABA vienen con código INDEC 2001-2015.
COD_CABA_MIN, COD_CABA_MAX = 2001, 2015


def cargar_viajes_a_caba() -> pd.DataFrame:
    if not VIAJES.exists():
        sys.exit(f"Falta {VIAJES}\n  Ver el docstring: se baja de BA Data, 8,8MB.")
    v = pd.read_excel(VIAJES)
    d = v[v.cod_partido_destino.between(COD_CABA_MIN, COD_CABA_MAX)].copy()
    d["comuna"] = d.cod_partido_destino - 2000
    # "de afuera" = el viaje no empezó en la misma comuna. Es la aproximación
    # más directa a población presente que no reside en la unidad.
    d["de_afuera"] = d.cod_partido_origen != d.cod_partido_destino
    return d


def main() -> None:
    d = cargar_viajes_a_caba()
    c = pd.DataFrame(json.loads(COMUNAS.read_text(encoding="utf-8"))).set_index("comuna")

    # PONDERA es el factor de expansión de la encuesta
    c["n_muestra"] = d.groupby("comuna").size()
    c["viajes_fuera"] = d[d.de_afuera].groupby("comuna").PONDERA.sum()
    c["fuera_por_hab"] = c.viajes_fuera / c.poblacion

    rho = c.presion_visitantes.corr(c.fuera_por_hab, method="spearman")

    print(f"ENMODO 2018: {len(d):,} viajes con destino en CABA "
          f"({c.n_muestra.min()}-{c.n_muestra.max()} por comuna)\n")
    print(c.sort_values("fuera_por_hab", ascending=False)[
        ["n_muestra", "fuera_por_hab", "presion_visitantes"]]
        .round({"fuera_por_hab": 2, "presion_visitantes": 2}).to_string())

    print(f"\nSpearman presion vs ENMODO: {rho:.3f}")

    # dónde discrepan: el índice ve subte y bici, no tren ni colectivo
    c["rank_enmodo"] = c.fuera_por_hab.rank(ascending=False)
    c["rank_presion"] = c.presion_visitantes.rank(ascending=False)
    c["brecha"] = c.rank_presion - c.rank_enmodo
    print("\nDonde más discrepan (brecha > 0 = el índice la subestima):")
    print(c.reindex(c.brecha.abs().sort_values(ascending=False).index)
          [["rank_enmodo", "rank_presion", "brecha"]].head(4).astype(int).to_string())

    if rho < 0.6:
        print("\nOJO: el acuerdo bajó de 0,6. El índice dejó de ordenar como "
              "la encuesta y habría que revisar la marca del tablero.")


if __name__ == "__main__":
    main()
