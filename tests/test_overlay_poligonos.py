"""
El test que la auditoría técnica pidió textualmente: "la suma de
población por hex dentro de un barrio debe igualar la población del
barrio". Esto habría atrapado en segundos el bug real de
overlay_poligonos.py (merge() antes de groupby().transform() desalineaba
índices, población total sumaba 20% de más) en vez de encontrarse por
inspección manual de un caso.

Corre sobre los parquet ya generados en data/features/ — no recalcula
el overlay (sería lento y depende de geopandas), valida el invariante
del resultado. Si alguien vuelve a romper esto, este test falla antes
de llegar al modelo.
"""

import pandas as pd
import pytest

from conftest import DATA_FEATURES, DATA_PROCESSED


@pytest.fixture
def hex_poblacion():
    path = DATA_FEATURES / "hex_poblacion.parquet"
    if not path.exists():
        pytest.skip("hex_poblacion.parquet no generado — correr src/etl/overlay_poligonos.py primero")
    return pd.read_parquet(path)


@pytest.fixture
def hex_maestra():
    return pd.read_parquet(DATA_FEATURES / "hex_maestra.parquet").dropna(subset=["barrio_id"])


@pytest.fixture
def poblacion_barrio():
    return pd.read_parquet(DATA_PROCESSED / "poblacion_barrio.parquet")


def test_poblacion_por_hex_suma_la_poblacion_real_del_barrio(hex_poblacion, hex_maestra, poblacion_barrio):
    conjunta = hex_poblacion.merge(hex_maestra[["hex_id", "barrio_id"]], on="hex_id")
    suma_por_barrio = conjunta.groupby(conjunta["barrio_id"].str.upper())["poblacion_hex"].sum()

    poblacion_barrio = poblacion_barrio.set_index("barrio")["poblacion"]

    comunes = suma_por_barrio.index.intersection(poblacion_barrio.index)
    assert len(comunes) >= 45  # de 48 barrios, casi todos deberían tener hex asignado

    diferencia_relativa = (suma_por_barrio[comunes] - poblacion_barrio[comunes]).abs() / poblacion_barrio[comunes]
    # tolerancia de punto flotante, no de lógica — si el bug del merge()
    # reapareciera, la diferencia sería ~20%, no ~0.001%
    assert (diferencia_relativa < 0.001).all(), (
        f"Barrios con población por hex que no cuadra con la real: "
        f"{diferencia_relativa[diferencia_relativa >= 0.001].to_dict()}"
    )


def test_poblacion_por_hex_no_tiene_negativos_ni_nulos_en_hex_validos(hex_poblacion, hex_maestra):
    conjunta = hex_poblacion.merge(hex_maestra[["hex_id"]], on="hex_id")
    assert conjunta["poblacion_hex"].notna().all()
    assert (conjunta["poblacion_hex"] >= 0).all()


def test_pct_espacio_verde_en_rango_0_a_1():
    path = DATA_FEATURES / "hex_espacios_verdes.parquet"
    if not path.exists():
        pytest.skip("hex_espacios_verdes.parquet no generado")
    verdes = pd.read_parquet(path)
    assert verdes["pct_espacio_verde"].between(0, 1).all()
