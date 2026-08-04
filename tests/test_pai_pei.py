"""Tests de propiedad para pai_pei() (train_baseline.py) — la métrica
estándar de la literatura de hotspot policing (Chainey et al. 2008)
agregada en el P0 de la auditoría. Se valida con casos de respuesta
conocida, no contra el modelo real."""

import pandas as pd
import pytest

from train_baseline import TARGET, pai_pei


def _tabla(hex_ids, real, predicho):
    return pd.DataFrame({"hex_id": hex_ids, TARGET: real, "predicho": predicho})


def test_pai_es_1_cuando_el_ranking_no_concentra_nada():
    """Si el riesgo real está distribuido perfectamente parejo entre
    todos los hexágonos, cualquier top-k% captura exactamente k% del
    riesgo — PAI debe dar 1.0 (ni mejor ni peor que azar)."""
    n = 100
    tabla = _tabla([f"h{i}" for i in range(n)], real=[1] * n, predicho=list(range(n)))
    pai, _ = pai_pei(tabla, "predicho", k=0.2)
    assert pai == pytest.approx(1.0, abs=1e-6)


def test_pai_mayor_a_1_cuando_el_modelo_concentra_bien():
    """El modelo pone los hexágonos con más delitos reales primero -> el
    top-k% debería capturar más que k% del riesgo, PAI > 1."""
    n = 100
    real = [10 if i < 20 else 0 for i in range(n)]  # todo el riesgo real en los primeros 20
    predicho = [100 - i for i in range(n)]  # el modelo también los rankea primero
    tabla = _tabla([f"h{i}" for i in range(n)], real, predicho)
    pai, _ = pai_pei(tabla, "predicho", k=0.2)
    assert pai == pytest.approx(5.0, abs=0.1)  # captura el 100% del riesgo en el 20% del área -> 1.0/0.2 = 5


def test_pei_es_1_cuando_el_modelo_iguala_al_hindsight():
    """Si el ranking del modelo es idéntico al ranking por delito real
    (el mejor caso posible), PEI tiene que dar exactamente 1.0."""
    n = 50
    real = list(range(n, 0, -1))  # 50, 49, ..., 1
    predicho = real  # el modelo predice exactamente el orden real
    tabla = _tabla([f"h{i}" for i in range(n)], real, predicho)
    _, pei = pai_pei(tabla, "predicho", k=0.3)
    assert pei == pytest.approx(1.0, abs=1e-6)


def test_pei_menor_a_1_cuando_el_modelo_rankea_al_reves():
    """Un modelo que rankea al revés del real (peor caso posible) tiene
    que dar PEI bajo, nunca >= al del modelo perfecto."""
    n = 50
    real = list(range(n, 0, -1))
    predicho = list(range(n))  # orden invertido
    tabla = _tabla([f"h{i}" for i in range(n)], real, predicho)
    _, pei = pai_pei(tabla, "predicho", k=0.3)
    assert pei < 1.0
