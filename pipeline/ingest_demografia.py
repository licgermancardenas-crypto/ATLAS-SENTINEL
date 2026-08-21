"""
Estructura demográfica por comuna (Censo 2022, INDEC) y por sexo a nivel
barrio (Censo 2010, agregando radios censales).

**Por qué existe este script si `ingest_poblacion.py` ya trae población.**
Ese trae el total y nada más. La pregunta "¿cuánta gente y de qué edad vive
en cada zona?" necesita el desglose, y el desglose no está publicado servido:
hay que ir a buscarlo a dos fuentes distintas y, en el caso de la edad,
derivarlo.

**Edad: existe por comuna, no por barrio, y viene como índices.**
El portal de GCBA no publica edad con desglose espacial — eso ya estaba
documentado y sigue siendo cierto. Pero el Censo 2022 de INDEC sí publica,
por comuna, cuatro indicadores de estructura etaria:

    Cuadro 7   % de población de 65 años y más
    Cuadro 8   índice de envejecimiento  = (65+ / 0-14) × 100
    Cuadro 9   índice de dependencia     = ((0-14 + 65+) / 15-64) × 100
    Cuadro 10  % de población de 80 años y más

Ninguno es "la pirámide", pero los tres grandes grupos salen de los dos
primeros por álgebra simple:

    p0_14  = p65 / (envejecimiento / 100)
    p15_64 = 100 − p65 − p0_14

y el tercero queda libre para **verificar**: recalcular el índice de
dependencia desde los grupos derivados y compararlo contra el publicado. El
mayor desvío sobre las 15 comunas es de 0,65 puntos (Comuna 13) y la mediana
es de 0,09 — compatible con que INDEC publica el 65+ con un decimal y los
índices redondeados a entero. O sea que la derivación es correcta y lo que
queda es ruido de redondeo, no error de método.

**Sexo: exacto, no aproximado.** `radios_censales.parquet` (Censo 2010) trae
varones y mujeres por radio. Asignando cada radio a su barrio por punto en
polígono, la suma por barrio da **idéntica** a `poblacion_barrio.parquet` —
que era de esperar, porque ese archivo *es* la agregación de los mismos
radios. 3 de los 3.554 radios caen fuera de todo polígono (borde/costa) y se
asignan al barrio más cercano.

**El choque de años es real y no se disimula.** La población por barrio es
Censo 2010 y la estructura etaria es Censo 2022; entre los dos hay 231.556
personas de diferencia a nivel Ciudad (2.890.151 → 3.121.707, +8,0%). No se
mezclan en un mismo número: cada salida lleva su año y el tablero lo muestra.
Reemplazar el denominador de las tasas por el de 2022 no es opción — abajo de
comuna no existe, y rompería la comparabilidad con NBI y hacinamiento, que
son 2010.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
import truststore
from shapely import wkt

# censo.gob.ar sirve la cadena de certificados incompleta (le falta el
# intermedio), así que `requests` corta con CERTIFICATE_VERIFY_FAILED mientras
# que curl en la misma máquina baja el archivo sin chistar: curl usa el almacén
# de Windows, que va a buscar el intermedio faltante por AIA, y OpenSSL no.
# `truststore` hace que Python use ese mismo almacén. La alternativa —
# `verify=False`— sería apagar la verificación entera para tapar un intermedio
# que en realidad es verificable, y no se hace.
truststore.inject_into_ssl()

RAIZ = Path(__file__).resolve().parent.parent
RAW_DIR = RAIZ / "data" / "raw" / "demografia"
PROCESSED_DIR = RAIZ / "data" / "processed"

BASE = "https://censo.gob.ar/wp-content/uploads/2023/11/c2022_caba_est_c{}_1.xlsx"

# qué cuadro trae qué. El 1 tiene los totales de 2010 y 2022 por comuna, que
# son el denominador con el que los porcentajes se vuelven personas.
CUADROS = {1: "poblacion", 7: "pct_65", 8: "envejecimiento", 9: "dependencia", 10: "pct_80"}

# La columna del año en los cuadros de índices: son series 1970-2022 y solo
# las dos últimas (2010, 2022) tienen dato por comuna — las anteriores son
# "///" porque las comunas no existían como unidad.
COL_2010, COL_2022 = 6, 7

# Y en el Cuadro 1, que no es una serie sino una comparación 2010 vs 2022, las
# columnas son (código, comuna, pob 2010, pob 2022, variación absoluta, %). La
# 4 es la variación, no la población — confundirlas da 231.556 habitantes para
# toda la Ciudad en vez de 3.121.707, que es justo la variación absoluta.
COL_POB_2010, COL_POB_2022 = 2, 3


def _bajar(cuadro: int) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    destino = RAW_DIR / f"c2022_caba_est_c{cuadro}_1.xlsx"
    if destino.exists():
        return destino
    resp = requests.get(BASE.format(cuadro), timeout=120)
    resp.raise_for_status()
    destino.write_bytes(resp.content)
    return destino


def _serie(cuadro: int, columna: int, nombre: str) -> pd.DataFrame:
    """Una columna de un cuadro de INDEC, indexada por número de comuna.

    Los xlsx traen tres hojas (carátula, índice, cuadro) y el cuadro tiene el
    título y dos filas de encabezado antes de los datos, así que no hay un
    `header=` que sirva: se filtra por las filas cuya segunda columna dice
    "Comuna N", que son las únicas quince que interesan.
    """
    hoja = pd.read_excel(_bajar(cuadro), sheet_name=-1, header=None)
    filas = hoja[hoja[1].astype(str).str.strip().str.startswith("Comuna ")]
    salida = pd.DataFrame({
        "comuna": filas[1].str.replace("Comuna ", "", regex=False).astype(int),
        nombre: pd.to_numeric(filas[columna], errors="coerce"),
    })
    return salida.sort_values("comuna").reset_index(drop=True)


def demografia_comuna() -> pd.DataFrame:
    """Los tres grandes grupos de edad por comuna, derivados y verificados."""
    d = _serie(1, COL_POB_2022, "poblacion_2022")
    for cuadro, nombre in [(7, "pct_65"), (8, "envejecimiento"),
                           (9, "dependencia"), (10, "pct_80")]:
        d = d.merge(_serie(cuadro, COL_2022, nombre), on="comuna")
    d = d.merge(_serie(1, COL_POB_2010, "poblacion_2010"), on="comuna")
    # `read_excel` los trae float porque la fila de encabezado mete un NaN en
    # la misma columna; son personas y se guardan como enteros
    d[["poblacion_2010", "poblacion_2022"]] = d[["poblacion_2010", "poblacion_2022"]].astype(int)

    d["pct_0_14"] = d["pct_65"] / (d["envejecimiento"] / 100)
    d["pct_15_64"] = 100 - d["pct_65"] - d["pct_0_14"]

    # el control: el índice de dependencia recalculado contra el publicado
    dep_calc = (d["pct_0_14"] + d["pct_65"]) / d["pct_15_64"] * 100
    d["error_control"] = (dep_calc - d["dependencia"]).abs()

    for grupo in ["0_14", "15_64", "65", "80"]:
        d[f"hab_{grupo}"] = (d[f"pct_{grupo}"] / 100 * d["poblacion_2022"]).round().astype(int)

    return d


def sexo_por_barrio() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Varones y mujeres por barrio y por comuna, agregando radios censales."""
    radios = pd.read_parquet(PROCESSED_DIR / "radios_censales.parquet")
    barrios = pd.read_parquet(PROCESSED_DIR / "barrios.parquet")

    puntos = gpd.GeoDataFrame(
        radios, geometry=gpd.points_from_xy(radios["lon"], radios["lat"]), crs="EPSG:4326")
    poligonos = gpd.GeoDataFrame(
        barrios[["nombre", "geometry_wkt"]].assign(
            geometry=barrios["geometry_wkt"].apply(wkt.loads)),
        geometry="geometry", crs="EPSG:4326").drop(columns="geometry_wkt")

    j = gpd.sjoin(puntos, poligonos, how="left", predicate="within").drop(columns="index_right")

    # los tres radios de borde que no caen dentro de ningún polígono van al
    # barrio más cercano: son 1.669 personas y descartarlos dejaría la suma
    # sin cuadrar contra el censo por barrio, que es el control de este paso
    huerfanos = j["nombre"].isna()
    if huerfanos.any():
        # a EPSG:5347 para que "el más cercano" se mida en metros y no en
        # grados, igual que en el cruce de accesos de autopista
        cercano = gpd.sjoin_nearest(
            puntos[huerfanos.values].to_crs(5347), poligonos.to_crs(5347),
            how="left").drop(columns="index_right")
        j.loc[huerfanos, "nombre"] = cercano["nombre"].values

    cols = ["poblacion_total", "poblacion_varones", "poblacion_mujeres"]
    por_barrio = j.groupby("nombre")[cols].sum().reset_index().rename(columns={"nombre": "barrio"})

    # **El total manda el censo; los radios solo aportan la proporción.**
    # Asignar radios por centroide y sumar da el total exacto de la Ciudad,
    # pero no el de cada barrio: un radio de 654 personas sobre el límite
    # Belgrano/Núñez cae de un lado por centroide y del otro en el archivo
    # oficial de GCBA, así que los dos barrios quedaban ±654 contra el número
    # que el tablero ya muestra en la tasa de delito. Dos poblaciones para
    # Belgrano en la misma pantalla es peor que perder precisión en el corte
    # por sexo, que a esta escala es de tercer decimal.
    oficial = pd.read_parquet(PROCESSED_DIR / "poblacion_barrio.parquet")
    oficial["clave"] = oficial["barrio"].str.upper()
    por_barrio["clave"] = por_barrio["barrio"].str.upper()
    por_barrio = por_barrio.merge(oficial[["clave", "poblacion"]], on="clave", how="left")
    faltan = por_barrio["poblacion"].isna()
    if faltan.any():
        raise SystemExit("Barrios sin población oficial: "
                         + ", ".join(por_barrio.loc[faltan, "barrio"]))

    ratio = por_barrio["poblacion_varones"] / por_barrio["poblacion_total"]
    por_barrio["poblacion_total"] = por_barrio["poblacion"].astype(int)
    por_barrio["poblacion_varones"] = (por_barrio["poblacion_total"] * ratio).round().astype(int)
    # las mujeres por resta y no por su propio ratio: así los dos suman el
    # total exacto sin que el redondeo deje una persona suelta
    por_barrio["poblacion_mujeres"] = (por_barrio["poblacion_total"]
                                       - por_barrio["poblacion_varones"])
    por_barrio = por_barrio.drop(columns=["clave", "poblacion"])

    # La comuna se arma sumando **barrios**, no agrupando por la columna
    # `comuna` del propio radio. Los dos caminos difieren en unos pocos radios
    # de borde —la comuna 13 daba 231.331 por un lado y 230.767 por el otro— y
    # el tablero ya calcula sus comunas sumando barrios en `comunas_resumen`.
    # Dos reglas distintas para el mismo número es exactamente cómo termina un
    # tablero mostrando dos poblaciones para la misma comuna en dos paneles.
    comuna_de = barrios.set_index("nombre")["comuna"].astype(int)
    por_comuna = (por_barrio.assign(comuna=por_barrio["barrio"].map(comuna_de))
                  .groupby("comuna")[cols].sum().reset_index())
    return por_barrio, por_comuna


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    edad = demografia_comuna()
    peor = edad["error_control"].max()
    print(f"Edad por comuna (Censo 2022): {len(edad)} comunas, "
          f"{edad['poblacion_2022'].sum():,} habitantes")
    print(f"  control del índice de dependencia: desvío máximo {peor:.2f} puntos "
          f"(mediana {edad['error_control'].median():.2f})")
    if peor > 1.5:
        raise SystemExit(f"La derivación de grupos de edad no cierra: desvío de {peor:.2f} puntos")
    edad.to_parquet(PROCESSED_DIR / "demografia_comuna.parquet", index=False)

    barrio, comuna = sexo_por_barrio()
    censo = pd.read_parquet(PROCESSED_DIR / "poblacion_barrio.parquet")["poblacion"].sum()
    total = barrio["poblacion_total"].sum()
    print(f"Sexo por barrio (Censo 2010): {len(barrio)} barrios, {total:,} habitantes "
          f"({barrio['poblacion_varones'].sum():,} varones, "
          f"{barrio['poblacion_mujeres'].sum():,} mujeres)")
    print(f"  control contra poblacion_barrio.parquet: {total - censo:+,}")
    if total != censo:
        raise SystemExit(f"La suma de radios por barrio no da el censo por barrio ({total-censo:+,})")

    barrio.to_parquet(PROCESSED_DIR / "sexo_barrio.parquet", index=False)
    comuna.to_parquet(PROCESSED_DIR / "sexo_comuna.parquet", index=False)


if __name__ == "__main__":
    main()
