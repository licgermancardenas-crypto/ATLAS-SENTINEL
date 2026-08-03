# ATLAS SENTINEL

Asistente de seguridad para conductores y planificación urbana en Buenos Aires (nombre de venta: **SIGE-BA**). Cruza delitos geolocalizados con datos de transporte (colectivos, EcoBici, subte), alumbrado público y siniestros viales para estimar riesgo por zona y horario — no solo un heatmap estático, sino un modelo núcleo espacio-temporal (grilla H3) del que se desprenden 3 módulos de decisión operativa (patrullas, cámaras, controles de acceso).

Arquitectura técnica completa del modelo: [`arquitectura-sige-ba.pdf`](arquitectura-sige-ba.pdf).

## Estructura

- `pipeline/` — scripts de ingesta y normalización de cada fuente de datos (Fase 1, completa)
- `data/features/` — tablas intermedias post-cruce espacial (hex_maestra, datasets con hex_id asignado) — no versionado en git, se regenera con `src/etl/`
- `src/etl/` — Capa 0: unificación espacio-temporal (grilla H3-8, asignación de hex_id/turno a cada dataset)
- `src/model_core/` — Capa 1: modelo núcleo de riesgo (XGBoost/LightGBM, objetivo Poisson)
- `src/optimization/` — Capa 2: módulos A/B/C (asignación de patrullas, cámaras nuevas, controles de acceso)
- `src/validation/` — Capa 3: SHAP, backtesting, métricas
- `src/export/` — genera los JSON/GeoJSON livianos que consume el dashboard
- `notebooks/` — exploración y validación de datos
- `models/`, `api/`, `web/` — carpetas del scaffold original; el plan vigente las reemplaza por `src/*` + `dashboard/` (Next.js, separado) — ver el PDF de arquitectura

## Fuentes de datos

| Fuente | Origen | Tamaño real |
|---|---|---|
| Delitos CABA | data.buenosaires.gob.ar/dataset/delitos | ~180MB (2016-2025) |
| Siniestros viales | data.buenosaires.gob.ar/dataset/victimas-siniestros-viales | ~16MB |
| Alumbrado LED | data.buenosaires.gob.ar/dataset/alumbrado-led | 9.4MB |
| Colectivos GTFS | data.buenosaires.gob.ar/dataset/colectivos-gtfs | 209MB |
| EcoBici recorridos | data.buenosaires.gob.ar/dataset/bicicletas-publicas | 2.0GB comprimido (crudo, no se guarda descomprimido) |
| Subte Molinetes | data.buenosaires.gob.ar/dataset/subte-viajes-molinetes | 1.1GB comprimido (crudo, no se guarda descomprimido) |
| Cámaras de control vehicular | data.buenosaires.gob.ar/dataset/camaras-fijas-control-vehicular | 15KB |
| Cajeros automáticos | data.buenosaires.gob.ar/dataset/cajeros-automaticos | 214KB |
| Establecimientos educativos | data.buenosaires.gob.ar/dataset/establecimientos-educativos | 1.1MB |
| Hospitales | data.buenosaires.gob.ar/dataset/hospitales | 15.6KB |
| Divisiones comisarías vecinales | data.buenosaires.gob.ar/dataset/divisiones-comisarias-vecinales | 2.5MB |
| Trenes GTFS | data.buenosaires.gob.ar/dataset/trenes-gtfs | 7.5MB descomprimido |
| Comisarías (ubicación puntual) | data.buenosaires.gob.ar/dataset/comisarias-policia-ciudad | 10KB |
| Universidades | data.buenosaires.gob.ar/dataset/universidades | 37KB |
| Espacios verdes públicos | data.buenosaires.gob.ar/dataset/espacios-verdes | 15MB |
| Socioeconómico por comuna (NBI + hacinamiento) | data.buenosaires.gob.ar (Instituto de Vivienda) | <1KB |
| Barrios (polígonos) | data.buenosaires.gob.ar/dataset/barrios | 651KB |
| Radios censales (Censo 2010) | data.buenosaires.gob.ar/dataset/informacion-censal-por-radio | 2.5MB |
| Población por comuna y por barrio | data.buenosaires.gob.ar/dataset/estructura-demografica y /barrios | <1KB c/u |
| Calles (callejero, con jerarquía vial) | data.buenosaires.gob.ar/dataset/calles | 10.6MB |
| Accesos por autopista (peajes/pórticos) | data.buenosaires.gob.ar/dataset/peajes-porticos-autopistas | <1KB |
| Estadios | data.buenosaires.gob.ar/dataset/estadios | 10KB |
| Eventos masivos (permisos) | data.buenosaires.gob.ar/dataset/permisos-eventos-masivos | ~230KB (5 años) |
| Clima diario | NASA POWER API (power.larc.nasa.gov) | ~130KB |

Los datos crudos no se versionan en git — se descargan localmente con los scripts de `pipeline/`.

## Estado de la ingesta

Las 6 fuentes previstas para la Fase 1 (riesgo + transporte) están completas, más 6 fuentes de contexto adicionales (POIs, cámaras, trenes).

| Fuente | Filas | Notas |
|---|---|---|
| Delitos | 1.353.136 | 2016-2025 |
| Siniestros viales | 63.081 hechos + 75.197 víctimas | 2019-2025 |
| Alumbrado LED | 102.700 luminarias | cobertura completa 15 comunas |
| Colectivos GTFS | 43.594 paradas, 1.052 ramales | feed sin actualizar desde 2019-09-30 |
| EcoBici | 48.222.663 viajes agregados, 570 estaciones | 2010-2026. Máquina de desarrollo con 3.4GB de RAM — todo se procesa en chunks y se agrega directo a "viajes por estación/hora/día de semana" en vez de guardar cada viaje. 2014 (~2% del histórico) queda afuera por tener un esquema propio sin id de estación ni coordenadas — ver nota en `pipeline/ingest_ecobici.py`. |
| Subte Molinetes | 2.799.213.945 pasajeros agregados, 90 estaciones | 2013-2025. 96.8% geolocalizado (matching por tokens + abreviaturas + alias manuales contra el dataset de estaciones, que usa nombres oficiales distintos a los de molinetes); el 3.2% restante son variantes de corrupción de encoding en nombres con Ñ/Ü — ver nota en `pipeline/ingest_molinetes.py`. |
| Cámaras de control vehicular | 224 | analítica de video + cinemómetros |
| Cajeros automáticos | 1.279 | |
| Establecimientos educativos | 2.767 | reproyectadas desde el sistema plano legacy "0 de Flores" (ver `pipeline/geo_utils.py`), ~100m de margen de error |
| Hospitales | 36 | públicos únicamente; mismo sistema de coordenadas que escuelas |
| Divisiones comisarías vecinales | 45 | son polígonos de zona de patrullaje, no la ubicación puntual de cada comisaría — se guarda el centroide + el polígono original en WKT |
| Comisarías (ubicación puntual) | 75 | complementa lo anterior con la dirección real de cada comisaría, lat/lon directo sin proyección rara |
| Trenes GTFS | 248 paradas, 27 ramales | único dataset que extiende cobertura más allá de CABA hacia el conurbano; feed sin actualizar desde 2020-02-10 |
| Universidades | 153 | lat/lon directo, sin proyección rara esta vez |
| Espacios verdes públicos | 2.176 (plazas, plazoletas, parques) | polígonos — se guarda centroide + WKT original para join espacial futuro |
| Socioeconómico por comuna | 15 comunas | % hogares con NBI + % hacinamiento. Sin coordenadas, se cruza por el campo "comuna" que ya existe en delitos/siniestros/alumbrado |
| Barrios | 48 | polígonos con comuna asignada — unidad intermedia entre comuna (15) y radio censal (3.554) para agrupar/mostrar riesgo |
| Radios censales | 3.554 | Censo 2010 — población total, sexo, viviendas, hogares y % NBI por radio (~800 hab. c/u). Es el denominador que faltaba para "delitos per cápita" y la unidad más fina disponible con población real. Único mismatch de nombres detectado: dataset de población usa "BOCA", barrios.csv usa "LA BOCA" (corregido a mano en `pipeline/ingest_poblacion.py`) |
| Población por comuna / por barrio | 15 comunas + 48 barrios | comuna es estimación 2017 (complementa NBI/hacinamiento, que no traía población total); barrio es censo 2010, mismo año que radios censales |
| Calles (callejero) | 31.961 tramos | trae jerarquía vial (troncal/distribuidora/local) y sentido de circulación; 1.729 tramos sin comuna asignada (autopistas/bordes). Columna "long" del origen es largo del tramo en metros, no longitud — ver nota en `pipeline/ingest_calles.py` |
| Accesos por autopista | 11 peajes/pórticos | AU Illia, Perito Moreno, Dellepiane, 25 de Mayo, Paseo del Bajo |
| Estadios | 30 | mismo sistema de coordenadas legacy que escuelas/hospitales |
| Eventos masivos | 2.898 permisos | 2019 + 2023-2026 (2020-2022 no publicados). Esquema distinto en cada archivo — ver notas de calidad abajo |
| Clima diario | 3.866 días (2016-01-01 a hoy) | NASA POWER, punto único (Obelisco) — no diferencia microclima entre barrios |

### Datos que se buscaron y no existen como abiertos

Cantidad de efectivos/oficiales, cantidad de móviles/patrullas disponibles, ubicación de radares móviles de velocidad, y la red completa de cámaras de seguridad urbana (más allá de las 224 de control vehicular) **no están publicados** — es información operativa de seguridad que el gobierno no divulga en detalle, tiene sentido que no exista. "Botones antipánico" sí existe pero es solo un total anual a nivel ciudad, sin geolocalización, no sirve para el modelo.

Nivel de ingreso y tasa de desempleo tampoco existen desglosados por comuna/barrio — solo hay totales a nivel ciudad por año (útiles para contexto, inútiles para diferenciar riesgo entre zonas). Se usan NBI y hacinamiento como proxies de vulnerabilidad socioeconómica en su lugar, que sí tienen ese desglose.

Series históricas diarias del Servicio Meteorológico Nacional **no son automatizables**: su único endpoint público estable solo da tiempo actual + pronóstico a 5 días, y la página de descarga de históricos está detrás de Cloudflare. Se usa NASA POWER como reemplazo (satelital, no estación puntual) — ver `pipeline/ingest_clima.py`.

Segmentación de población por edad/sexo **tampoco existe por zona**: el único dataset de estructura etaria de GCBA (`estructura-demografica/est_pob_sexo...`) es serie histórica 1855-presente a nivel ciudad completa, sin ningún desglose espacial — no sirve para diferenciar riesgo entre zonas y no se ingesta. Censo 2022 por radio tampoco está publicado en este portal (solo 2001 y 2010 a esa granularidad); si hace falta, habría que cruzar con el Portal Geoestadístico de INDEC, que usa otra cartografía/códigos.

### Lecciones de esta fase

Los datasets de transporte (EcoBici, Molinetes) cambiaron de esquema de columnas, delimitador, encoding o estructura de archivo **casi todos los años** — nada de esto está documentado en el portal de datos abiertos, se descubrió a fuerza de que el pipeline fallara con errores concretos. Cosas a tener en cuenta si se vuelve a correr la ingesta desde cero o se agregan años nuevos:

- Los scripts validan integridad de cada descarga (zip corrupto → se borra y re-descarga solo) porque el portal tiene caídas y timeouts de red frecuentes.
- No asumir que un ZIP tiene un solo archivo adentro — desde 2022 Molinetes viene partido en ~24-26 archivos por año.
- No asumir el mismo delimitador o encoding entre años de la misma fuente.
- Los joins por nombre de estación (texto libre) contra datasets de referencia nunca son 100% exactos — documentar el % sin matchear en vez de asumir cobertura total.
- **GCBA usa dos sistemas de coordenadas planas distintos entre datasets, sin documentarlo**: siniestros viales usa GKBA (Gauss-Krüger CABA 2019, oficial desde 2019), pero escuelas y hospitales todavía usan un sistema previo ("0 de Flores"). Aplicar la fórmula de uno al otro tira puntos a 90km de distancia sin ningún error visible en el código — solo se nota si se valida el rango de lat/lon contra los límites reales de la ciudad. Se calibraron ambos cruzando direcciones conocidas contra el geocodificador oficial de GCBA (`ws.usig.buenosaires.gob.ar`) en vez de confiar en el código EPSG que documenta el portal (9497), que ni siquiera existe en las bases de PROJ. Ver `pipeline/geo_utils.py`. Estadios (agregado después) también usa el sistema legacy, no el nuevo.
- El dataset de eventos masivos tiene **tres esquemas distintos en 5 archivos anuales** (2019 vs. 2023 vs. 2024-2026): cambia el delimitador, las columnas disponibles (barrio/aforo/lat-lon no están en todos) y hasta el encoding — el archivo 2023 es cp850 (DOS Latin US), el único de todo el proyecto que no es utf-8. Se detectó porque "Denominación" rompía el parser en utf-8 y en latin-1 daba un carácter distinto al esperado. Ver `pipeline/ingest_eventos_masivos.py`.
- No asumir que un nombre de columna es lo que parece: en el callejero, la columna "long" es el largo del tramo en metros, no longitud geográfica.

## Estado de Capa 0 (unificación espacio-temporal)

Grilla H3-8 generada sobre CABA (unión de los 48 barrios, no existe un dataset propio de "límite CABA"): **459 hexágonos** (`data/features/hex_maestra.parquet`), con `barrio_id`/`comuna_id` (point-in-polygon contra `barrios.parquet`) y `radio_censal_id` (contra `radios_censales.parquet`) por centroide. 58 hexágonos de borde/costa no caen dentro de ningún barrio (agua, terraplenes) — quedan sin `barrio_id`/`comuna_id`, es correcto que así sea.

`h3.polygon_to_cells` con el modo por default (`contain="center"`, solo hexágonos cuyo *centro* cae adentro del polígono) dejaba 1-6% de los puntos de delitos/siniestros/alumbrado fuera de la grilla — puntos reales de CABA cerca de la costa caían en hexágonos de borde cuyo centro quedaba just afuera. Se cambió a `polygon_to_cells_experimental(..., contain="overlap")` (cualquier hexágono que toque el polígono, aunque sea parcial) y el problema bajó a <0,5%.

Datasets ya cruzados con hex_id (`src/etl/assign_hex_puntual.py`, `assign_hex_calles.py`): delitos, siniestros_hechos, cámaras, alumbrado, cajeros, comisarías (ubicación puntual), escuelas, hospitales, universidades, estadios, ecobici/molinetes (estaciones), calles (por el punto medio del tramo, ya calculado en `pipeline/ingest_calles.py`), accesos_autopistas (+ tramo de calle troncal más cercano, reproyectado a EPSG:5347 para que la distancia sea en metros reales). Eventos masivos también pasó por el script pero solo 129 de 2.898 filas tienen hex_id (las de 2019, únicas con lat/lon) — el resto (2023-2026) solo tiene barrio, que es un tipo de cruce distinto (join por nombre, no point-in-hex), pendiente.

Pendiente, y son operaciones distintas a point-in-hex (no encajan en `asignar_hex_id`): **espacios_verdes** y **comisarias.parquet** (el de zonas de patrullaje) necesitan overlay de polígono contra la grilla (% de área, no un punto); **población por hex** (denominador per cápita) sale de prorratear `poblacion_comuna`/`poblacion_barrio` por área, aunque ya se puede aproximar sin prorratear porque `hex_maestra` ya tiene `radio_censal_id` — un join directo contra `radios_censales.poblacion_total` alcanza para una primera versión.

Gotchas encontrados: `siniestros_hechos` guarda lat/lon como texto, no float (se castea en `hex_utils.asignar_hex_id`); `hora_siniestro` viene como "HH:MM:SS" mientras que `franja` de delitos ya es un número 0-23 (se resuelve en `hex_utils.turno_desde_hora`, detecta el formato).
