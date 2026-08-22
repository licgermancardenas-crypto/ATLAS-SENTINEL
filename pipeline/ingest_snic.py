"""
Víctimas por sexo del SNIC (Sistema Nacional de Información Criminal,
Ministerio de Seguridad de la Nación) para CABA.

**Por qué hace falta otra fuente de delito si el proyecto ya tiene una.**
`delitos_hex` son 1,35M de hechos georreferenciados y no trae **ni un
atributo del damnificado**: se verificó contra los CSV crudos de los diez
años y las quince columnas son las mismas en 2016 y en 2025. Con esos datos
no se puede contestar "¿a quién le pasa?", que es la primera pregunta que
hace cualquiera frente al mapa demográfico.

El SNIC sí registra víctimas, y **este script existe para poder decir con
precisión hasta dónde llega y dónde se corta**:

- **Trae sexo. No trae edad.** Ninguna columna de edad, en ninguna categoría,
  en veintiséis años de serie. La pregunta por edad no es difícil: no tiene
  datos públicos.
- **La unidad más fina es la provincia** —CABA entera—, así que nada de esto
  se puede mapear ni cruzar con el filtro de comuna o barrio del tablero. La
  base por departamentos no está publicada.
- **Robos, hurtos y amenazas registran CERO víctimas.** No es que falten
  algunas: el SNIC solo carga víctimas en delitos contra las personas, así
  que sobre ~517.000 hechos de robo y hurto en CABA (2022-2025) no hay una
  sola víctima caracterizada. Justo los dos tipos que dominan el tablero.
- **Donde sí hay dato, el "sin dato" es enorme**: 26% a 44% en las
  categorías grandes, y 74% o 92% en algunas chicas. Solo homicidios y
  suicidios están completos.

Nada de eso es motivo para no publicarlo — es motivo para publicarlo con los
tres números a la vista (varones, mujeres, sin dato) en vez de un porcentaje
que esconda el denominador.

Fuente: https://cloud-snic.minseg.gob.ar/Bases/SNIC/snic-provincias.csv
Salida: `data/processed/snic_victimas_caba.parquet`
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests
import truststore

truststore.inject_into_ssl()

URL = "https://cloud-snic.minseg.gob.ar/Bases/SNIC/snic-provincias.csv"

RAIZ = Path(__file__).resolve().parent.parent
RAW_DIR = RAIZ / "data" / "raw" / "snic"
PROCESSED_DIR = RAIZ / "data" / "processed"

# El id de provincia de CABA en la nomenclatura de INDEC que usa el SNIC. Se
# filtra por id y no por nombre porque el nombre viene con acentos y ha
# cambiado de forma entre ediciones ("Ciudad Autónoma de Buenos Aires").
PROVINCIA_CABA = 2

COLS = ["anio", "codigo_delito_snic_nombre", "cantidad_hechos", "cantidad_victimas",
        "cantidad_victimas_masc", "cantidad_victimas_fem", "cantidad_victimas_sd"]


def descargar() -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    destino = RAW_DIR / "snic-provincias.csv"
    if destino.exists():
        return destino
    resp = requests.get(URL, timeout=180)
    resp.raise_for_status()
    destino.write_bytes(resp.content)
    return destino


def main() -> None:
    # separador ';' y decimal ',' — es un CSV argentino, no uno anglosajón
    d = pd.read_csv(descargar(), sep=";", encoding="utf-8", decimal=",")
    caba = d[d["provincia_id"] == PROVINCIA_CABA][COLS].copy()
    caba = caba.rename(columns={"codigo_delito_snic_nombre": "delito"})
    for c in ["cantidad_hechos", "cantidad_victimas", "cantidad_victimas_masc",
              "cantidad_victimas_fem", "cantidad_victimas_sd"]:
        caba[c] = pd.to_numeric(caba[c], errors="coerce").fillna(0)

    # control: los tres desgloses tienen que sumar el total de víctimas. Si no
    # cierra, el corte por sexo que publique el tablero estaría mal por
    # construcción y es mejor cortar acá que mostrarlo.
    suma = (caba["cantidad_victimas_masc"] + caba["cantidad_victimas_fem"]
            + caba["cantidad_victimas_sd"])
    desvio = (suma - caba["cantidad_victimas"]).abs().max()
    if desvio > 0.5:
        raise SystemExit(f"masc+fem+sd no suma el total de víctimas (desvío máximo {desvio}).")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    caba.to_parquet(PROCESSED_DIR / "snic_victimas_caba.parquet", index=False)

    ult = caba[caba["anio"] >= caba["anio"].max() - 3]
    con_victimas = ult[ult["cantidad_victimas"] > 0]["delito"].nunique()
    sin_victimas = ult[ult["cantidad_victimas"] == 0]
    print(f"SNIC CABA: {caba['anio'].min()}-{caba['anio'].max()}, {len(caba)} filas")
    print(f"  últimos 4 años: {con_victimas} categorías con víctimas caracterizadas, "
          f"{sin_victimas['delito'].nunique()} sin ninguna "
          f"({sin_victimas['cantidad_hechos'].sum():,.0f} hechos)")
    print(f"  control masc+fem+sd = total: desvío máximo {desvio}")


if __name__ == "__main__":
    main()
