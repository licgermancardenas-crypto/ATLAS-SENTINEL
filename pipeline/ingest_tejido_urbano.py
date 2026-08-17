"""
Descarga y prepara el Tejido Urbano de CABA — la ciudad construida en 3D.

(data.buenosaires.gob.ar/dataset/tejido-urbano, Secretaría de Desarrollo Urbano)

QUÉ ES ESTE DATASET
1.386.616 polígonos con la **altura en metros** de cada volumen construido de la
Ciudad, levantados por fotogrametría por la Secretaría de Planeamiento. Es el
insumo del módulo 3D: sin esto habría que estimar alturas, y la alternativa
—OSM— tiene las huellas pero solo el 7% de los edificios con altura declarada
(medido sobre el microcentro, que es la zona mejor mapeada).

DOS COSAS QUE HAY QUE ENTENDER ANTES DE USARLO

1. **No es un polígono por edificio, son 4,5 por parcela.** Hay 309.169
   parcelas (`smp` = sección-manzana-parcela) y cada una viene partida en los
   volúmenes que la componen: el frente de 2,8 m, el cuerpo de 25,2 m, la
   medianera de 5,6 m. Cada polígono es un prisma desde el suelo hasta su
   `altura`, y por eso se extruyen tal cual, sin agrupar — agrupar por parcela
   aplanaría justamente el escalonado que hace que la silueta se vea como la
   ciudad real.

2. **Las alturas son múltiplos de 2,8 m**, que es el piso tipo: los valores son
   2,8 / 5,6 / 11,2 / 25,2. O sea que la fuente cuenta pisos y multiplica, no
   mide el edificio. Sirve perfecto para volumetría; no lo uses como cota real.

LIMPIEZA, Y POR QUÉ CADA COSA
- **Alturas imposibles.** El máximo del dataset es 830 m. El edificio más alto
  de la Ciudad (Alvear Tower) ronda los 235 m, así que todo lo que pase de 240 m
  es error de fotogrametría y se recorta ahí. Son poquísimos casos, pero uno
  solo arruina la escala visual de toda la vista.
- **Astillas.** El 27% de los polígonos mide menos de 10 m²: patios internos,
  retiros, restos de la partición por parcela. A la escala en que se mira la
  ciudad no se ven, y son un cuarto del peso del archivo. Se descartan.
- **El dato es hasta 2021**, según el propio portal. Para volumetría urbana da
  igual (la ciudad construida no se mueve rápido), pero conviene saberlo antes
  de cruzarlo con cualquier serie reciente.

SALIDA: DOS ARCHIVOS DE TESELAS, Y LA RAZÓN IMPORTA
Teselas vectoriales PMTiles, que es lo que hace viable mostrar la ciudad entera:
el navegador baja por rango HTTP solo las teselas que está mirando, en vez de
los ~100 MB del GeoJSON completo. Se generan con el GDAL que ya trae pyogrio
(driver PMTiles), así que no hace falta tippecanoe ni WSL.

Van dos archivos y no uno porque **el costo de teselar explota en los zooms
bajos**. La primera versión pedía z12-16 de una: a z12 la Ciudad entra en cuatro
teselas, o sea que el teselador tiene que meter 250.000 polígonos en cada una
para después descartar casi todos por el límite de tamaño de la tesela. Corrió
quince minutos, escribió 35 GB de reescrituras de SQLite y no había producido un
byte de salida. A z14 cada tesela lleva unos 5.000 polígonos y el mismo trabajo
tarda un rato razonable.

Entonces:
- `caba.pmtiles`       — todos los volúmenes, z14-16. Es el detalle de calle.
- `caba_hitos.pmtiles` — solo los de 40 m o más, z12-13. Son ~2% de los
  polígonos y alcanzan para que a escala de ciudad se lea la silueta (el eje de
  Catalinas, las torres de Puerto Madero, el Once) sin mover un millón de
  volúmenes que a ese zoom medirían menos de un píxel.

Uso: python ingest_tejido_urbano.py
"""

from __future__ import annotations

import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import geopandas as gpd
import requests

RAIZ = Path(__file__).resolve().parent.parent
CRUDO = RAIZ / "data" / "raw" / "tejido_urbano" / "tejido.zip"
PROCESADO = RAIZ / "data" / "processed" / "tejido_urbano.parquet"
TEJIDO_DIR = RAIZ / "dashboard" / "public" / "tejido"
TESELAS = TEJIDO_DIR / "caba.pmtiles"
TESELAS_HITOS = TEJIDO_DIR / "caba_hitos.pmtiles"

URL = ("https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
       "secretaria-de-desarrollo-urbano/tejido-urbano/tejido.zip")

ALTURA_MAX = 240.0     # m — por encima de esto es error de fotogrametría
AREA_MIN = 10.0        # m² — astillas invisibles a escala de ciudad
CRS_METRICO = 5347     # POSGAR 2007 / Argentina faja 5, para medir en metros

ZOOM_DETALLE = (14, 16)    # todos los volúmenes
ZOOM_HITOS = (12, 13)      # solo los altos, para la silueta a escala de ciudad
ALTURA_HITO = 40.0         # m — desde acá un edificio se lee a escala de ciudad


def descargar() -> None:
    """Baja el zip si no está. El recurso .geojson del portal devuelve 503 de
    forma consistente; el shapefile (.zip) sí responde, así que se usa ese."""
    if CRUDO.exists():
        print(f"[1] ya está: {CRUDO.name} ({CRUDO.stat().st_size / 1048576:.0f} MB)")
        return
    CRUDO.parent.mkdir(parents=True, exist_ok=True)
    print(f"[1] descargando {URL.rsplit('/', 1)[1]} (~161 MB)...")
    t0 = time.time()
    with requests.get(URL, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(CRUDO, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    print(f"    {CRUDO.stat().st_size / 1048576:.0f} MB en {time.time() - t0:.0f}s")


def cargar_y_limpiar() -> gpd.GeoDataFrame:
    print("[2] leyendo el shapefile (1,4 M de polígonos, tarda)...")
    t0 = time.time()
    g = gpd.read_file(f"zip://{CRUDO}!tejido/tejido.shp")
    print(f"    {len(g):,} polígonos en {time.time() - t0:.0f}s")

    antes = len(g)
    g = g[g["altura"] > 0]
    recortados = int((g["altura"] > ALTURA_MAX).sum())
    g["altura"] = g["altura"].clip(upper=ALTURA_MAX).round(1)

    # el área se mide proyectando: en grados no significa nada
    g["area_m2"] = g.to_crs(CRS_METRICO).area.round(1)
    g = g[g["area_m2"] >= AREA_MIN]

    print(f"    altura=0 y astillas <{AREA_MIN:.0f} m²: {antes:,} -> {len(g):,} "
          f"({1 - len(g) / antes:.1%} descartado)")
    print(f"    alturas recortadas a {ALTURA_MAX:.0f} m: {recortados}")
    print(f"    parcelas distintas: {g['smp'].nunique():,}")
    print(f"    altura  mediana {g['altura'].median():.1f} m  "
          f"p90 {g['altura'].quantile(0.9):.1f} m  máx {g['altura'].max():.1f} m")
    return g[["smp", "altura", "area_m2", "geometry"]]


def teselar(g: gpd.GeoDataFrame, destino: Path, zooms: tuple[int, int]) -> None:
    """Escribe un PMTiles. Solo `altura` viaja al navegador: `smp` y `area_m2`
    no se usan para dibujar y multiplicarían el peso de cada tesela."""
    for resto in (destino, Path(f"{destino}.tmp.mbtiles"),
                  Path(f"{destino}.tmp.mbtiles.temp.db")):
        resto.unlink(missing_ok=True)      # el driver no sobreescribe
    t0 = time.time()
    print(f"    {destino.name}: {len(g):,} volúmenes, z{zooms[0]}-{zooms[1]}...")
    g[["altura", "geometry"]].to_file(
        destino, driver="PMTiles", layer="tejido",
        MINZOOM=zooms[0], MAXZOOM=zooms[1],
    )
    print(f"      -> {destino.stat().st_size / 1048576:.1f} MB "
          f"en {time.time() - t0:.0f}s")


def escribir(g: gpd.GeoDataFrame) -> None:
    PROCESADO.parent.mkdir(parents=True, exist_ok=True)
    g.to_parquet(PROCESADO, index=False)
    print(f"[3] {PROCESADO.name}: {PROCESADO.stat().st_size / 1048576:.0f} MB")

    TEJIDO_DIR.mkdir(parents=True, exist_ok=True)
    print("[4] teselando...")
    hitos = g[g["altura"] >= ALTURA_HITO]
    print(f"    hitos (>= {ALTURA_HITO:.0f} m): {len(hitos):,} "
          f"({len(hitos) / len(g):.1%} del total)")
    # primero los hitos: es el más chico, así que si algo está mal se ve rápido
    teselar(hitos, TESELAS_HITOS, ZOOM_HITOS)
    teselar(g, TESELAS, ZOOM_DETALLE)


def main() -> None:
    descargar()
    g = cargar_y_limpiar()
    escribir(g)
    print(f"\nListo. El tablero los consume por rango HTTP desde /{TEJIDO_DIR.name}/")


if __name__ == "__main__":
    main()
