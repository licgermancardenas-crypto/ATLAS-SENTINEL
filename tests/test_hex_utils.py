"""Tests de src/etl/hex_utils.py — funciones puras, sin I/O."""

import h3
import pandas as pd
import pytest

from hex_utils import RESOLUCION_MODELO, asignar_hex_id, turno_desde_hora


def test_turno_desde_hora_cubre_las_24_horas_sin_solapar():
    """Cada hora 0-23 cae en exactamente uno de los 4 turnos — si dos
    turnos se solapan o queda una hora sin turno, un hex×turno del
    training table quedaría mal etiquetado silenciosamente."""
    horas = pd.Series(range(24))
    turnos = turno_desde_hora(horas)
    assert turnos.isna().sum() == 0
    assert set(turnos.unique()) == {"Mañana", "Tarde", "Noche", "Madrugada"}
    assert len(turnos) == 24  # una hora, un turno — nunca dos


def test_turno_desde_hora_limites_correctos():
    """Los bordes exactos de sección 1.2: Mañana 06-14 / Tarde 14-22 /
    Noche 22-02 / Madrugada 02-06."""
    casos = {5: "Madrugada", 6: "Mañana", 13: "Mañana", 14: "Tarde",
             21: "Tarde", 22: "Noche", 1: "Noche", 2: "Madrugada"}
    resultado = turno_desde_hora(pd.Series(list(casos.keys())))
    for turno_esperado, turno_real in zip(casos.values(), resultado):
        assert turno_esperado == turno_real


def test_turno_desde_hora_acepta_formato_hhmmss():
    """hora_siniestro viene como texto "HH:MM:SS", franja de delitos como
    número — la función tiene que detectar cuál es cuál (gotcha real
    documentado en build_training_table.py)."""
    horas_texto = pd.Series(["06:30:00", "14:15:00", "23:00:00"])
    turnos = turno_desde_hora(horas_texto)
    assert list(turnos) == ["Mañana", "Tarde", "Noche"]


def test_asignar_hex_id_castea_lat_lon_string():
    """siniestros_hechos guarda lat/lon como texto — asignar_hex_id no
    puede asumir float (gotcha real ya encontrado una vez)."""
    df = pd.DataFrame({"lat": ["-34.6037", "-34.5900"], "lon": ["-58.3816", "-58.4000"]})
    resultado = asignar_hex_id(df, "lat", "lon")
    assert resultado.notna().all()
    assert all(h3.is_valid_cell(h) for h in resultado)


def test_asignar_hex_id_devuelve_celdas_h3_validas_a_la_resolucion_del_modelo():
    df = pd.DataFrame({"lat": [-34.6037], "lon": [-58.3816]})
    hex_id = asignar_hex_id(df, "lat", "lon").iloc[0]
    assert h3.is_valid_cell(hex_id)
    assert h3.get_resolution(hex_id) == RESOLUCION_MODELO


def test_asignar_hex_id_nulo_para_coordenadas_faltantes():
    """Una fila sin lat/lon no debe hacer fallar todo el batch, ni
    inventar un hex_id — tiene que quedar explícitamente nula."""
    df = pd.DataFrame({"lat": [-34.6037, None], "lon": [-58.3816, None]})
    resultado = asignar_hex_id(df, "lat", "lon")
    assert resultado.iloc[0] is not None
    assert pd.isna(resultado.iloc[1])
