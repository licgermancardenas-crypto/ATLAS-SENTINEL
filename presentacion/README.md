# Material de presentación

Las páginas que se publican para mostrar el proyecto: una por cada módulo de
Capa 2 y una del análisis exploratorio. Son HTML autocontenido — sin librería de
gráficos, sin tile server, sin CDN, sin una sola request externa. Todo lo visual
(mapas, curvas, choropleths) se dibuja como SVG inline calculado desde los datos
del repo.

Esa restricción no es estética: el visor donde se publican corre bajo una CSP
que bloquea cualquier host externo. Un `<script src="https://...">` no falla con
un error visible, simplemente no carga y la página queda muda.

## Estructura

```
paginas/     fuente — HTML completo, con los marcadores de figura VACÍOS
build/       resultado — lo mismo con las figuras inyectadas (no se versiona)
```

Los generadores leen de `paginas/` y escriben en `build/`. La fuente nunca se
toca, así que el diff de un cambio de texto es el cambio de texto y no 1,5MB de
paths SVG movidos.

## Regenerar

```bash
python presentacion/gen_mapas.py      # mapas de los módulos A, B y C
python presentacion/gen_eda_figs.py   # las 9 figuras de la página del EDA
```

Ambos necesitan que el pipeline haya corrido: leen `dashboard/public/data/`
(riesgo por hexágono, salidas de los módulos) y `data/features/grafo_vial.graphml`,
que no están versionados.

Después de correrlos, lo publicable está en `build/`.

## Otros scripts

| Script | Para qué |
|---|---|
| `gen_notebook.py` | Arma y ejecuta `notebooks/01_eda_delitos.ipynb`. El notebook se genera desde acá para que el JSON quede bien formado y las salidas queden ya calculadas. |
| `css_mapa.py` | Reemplaza el bloque de CSS del mapa en las tres páginas de módulos, para que no haya que editarlas a mano una por una y queden idénticas. |
| `preview.py` | Renderiza el mapa de una página a PNG con matplotlib, leyendo los mismos paths SVG que se inyectaron. Sirve para revisar el resultado sin abrir un navegador. |

## Dónde viven los números

Ninguna de estas páginas calcula nada: todas las cifras salen de los scripts de
`src/` y están documentadas en el README de la raíz. Si un número de una página
no coincide con el README, la página está desactualizada — no al revés.
