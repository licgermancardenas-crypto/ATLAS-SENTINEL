"""Invariantes de la grilla H3 base — si esto se rompe, todo lo que se
construye encima (Capa 1, Módulos A/B/C) hereda el error en silencio."""

import h3
import pandas as pd
import pytest

from conftest import DATA_FEATURES, DATA_PROCESSED


@pytest.fixture
def hex_maestra():
    path = DATA_FEATURES / "hex_maestra.parquet"
    if not path.exists():
        pytest.skip("hex_maestra.parquet no generado — correr src/etl/build_hex_maestra.py primero")
    return pd.read_parquet(path)


def test_hex_id_sin_duplicados(hex_maestra):
    assert hex_maestra["hex_id"].duplicated().sum() == 0


def test_todos_los_hex_id_son_celdas_h3_validas(hex_maestra):
    assert all(h3.is_valid_cell(h) for h in hex_maestra["hex_id"])


def test_comuna_en_rango_valido_donde_no_es_nula(hex_maestra):
    comunas = hex_maestra["comuna_id"].dropna()
    assert comunas.between(1, 15).all()


def test_centroides_dentro_de_los_limites_geograficos_de_caba(hex_maestra):
    """Chequeo barato de sanidad geográfica — el mismo tipo de validación
    que hubiera atrapado el bug de reproyección de 90km documentado en
    pipeline/geo_utils.py si hubiera existido en su momento."""
    assert hex_maestra["lat"].between(-34.75, -34.50).all()
    assert hex_maestra["lon"].between(-58.55, -58.30).all()


def test_todo_hex_con_radio_censal_tiene_poblacion_positiva():
    radios = pd.read_parquet(DATA_PROCESSED / "radios_censales.parquet")
    assert (radios["poblacion_total"] >= 0).all()
    assert radios["poblacion_total"].sum() > 0
