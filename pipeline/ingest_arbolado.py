"""
Descarga y normaliza el Arbolado Público Lineal de CABA.

(data.buenosaires.gob.ar/dataset/arbolado-publico-lineal, relevamiento 2017-2018)

POR QUÉ ESTE DATASET
Es el censo de los árboles de vereda de la Ciudad: 370.180 ejemplares, cada uno
con **especie, altura y diámetro medidos**, no estimados. Entra al proyecto por
la vista 3D — una ciudad sin árboles se lee como maqueta, y Buenos Aires tiene
un árbol cada pocos metros de vereda — pero el dato sirve para más que dibujar:
la altura del arbolado tapa cámaras y luminarias, que es exactamente lo que
optimizan los Módulos B y A.

LO QUE TRAE Y LO QUE NO
Trae `altura_arbol` en metros y `diametro_altura_pecho` en centímetros. **No
trae el diámetro de la copa**, que es lo que haría falta para dibujar un árbol
con su tamaño real; eso se aproxima en `build_base_3d.py` y está marcado ahí
como aproximación de dibujo, no como dato.

Es un relevamiento de 2017-2018: los árboles crecieron desde entonces y algunos
ya no están. Para volumetría urbana alcanza; no lo uses para inventario actual.

Uso: python ingest_arbolado.py
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parent.parent
CRUDO = RAIZ / "data" / "raw" / "arbolado" / "arbolado-publico-lineal-2017-2018.csv"
PROCESADO = RAIZ / "data" / "processed" / "arbolado.parquet"

URL = ("https://cdn.buenosaires.gob.ar/datosabiertos/datasets/atencion-ciudadana/"
       "arbolado-publico-lineal/arbolado-publico-lineal-2017-2018.csv")

# El CDN corta el handshake TLS cada tanto (ConnectionError en el primer
# intento, bien en el segundo). Con reintentos deja de ser un problema.
INTENTOS = 5


def descargar() -> None:
    if CRUDO.exists():
        print(f"[1] ya está: {CRUDO.name} ({CRUDO.stat().st_size / 1048576:.0f} MB)")
        return
    CRUDO.parent.mkdir(parents=True, exist_ok=True)
    for i in range(1, INTENTOS + 1):
        try:
            print(f"[1] descargando (intento {i})...")
            r = requests.get(URL, timeout=300, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            CRUDO.write_bytes(r.content)
            print(f"    {CRUDO.stat().st_size / 1048576:.0f} MB")
            return
        except Exception as e:
            print(f"    falló: {type(e).__name__}")
            time.sleep(4 * i)
    raise RuntimeError("no se pudo descargar el arbolado")


def main() -> None:
    descargar()
    d = pd.read_csv(CRUDO, low_memory=False)
    print(f"[2] {len(d):,} ejemplares")

    antes = len(d)
    d = d.dropna(subset=["lat", "long", "altura_arbol"])
    d = d[(d["altura_arbol"] > 0) & (d["altura_arbol"] <= 40)]
    print(f"    sin coordenadas o sin altura: {antes:,} -> {len(d):,}")

    out = pd.DataFrame({
        "lat": d["lat"].astype("float32"),
        "lon": d["long"].astype("float32"),
        "altura_m": d["altura_arbol"].astype("float32"),
        "dap_cm": d["diametro_altura_pecho"].astype("float32"),
        "especie": d["nombre_cientifico"].fillna("No identificado"),
        "comuna": d["comuna"].astype("int16"),
    })
    PROCESADO.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(PROCESADO, index=False)

    print(f"    altura: mediana {out.altura_m.median():.0f} m, "
          f"p95 {out.altura_m.quantile(.95):.0f} m, máx {out.altura_m.max():.0f} m")
    print(f"    {out.especie.nunique()} especies; la más común, "
          f"{out.especie.value_counts().index[0]} "
          f"({out.especie.value_counts().iloc[0]:,} ejemplares)")
    print(f"[3] {PROCESADO.name}: {PROCESADO.stat().st_size / 1048576:.1f} MB")


if __name__ == "__main__":
    main()
